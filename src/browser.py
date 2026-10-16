import base64
import json
import math
import time
from pathlib import Path
from typing import Any, Callable

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from .common import language as lang


class Browser:
    def __init__(self, headless: bool = False, timeout: float = 30, chrome_binary: str | Path | None = None, language: str = "en") -> None:
        """To store Chrome and capture settings without launching a browser."""

        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite number greater than zero")
        self.headless = headless
        self.timeout = timeout
        self.chrome_binary = chrome_binary
        self.language = lang.normalize_language(language)
        self.driver: webdriver.Chrome | None = None
        self._completed_requests: set[str] = set()

    def start(self) -> None:
        """To start Chrome with the configured language and CDP network events enabled before navigation."""

        if self.driver is not None:
            raise RuntimeError("Browser has already started")
        options = webdriver.ChromeOptions()
        options.page_load_strategy = "none"
        locale = "en-US" if self.language == "en" else self.language
        base_language = self.language.split("-")[0]
        accept_languages = locale if locale == base_language else f"{locale},{base_language}"
        options.add_argument(f"--lang={locale}")
        options.add_argument("--window-size=1440,1000")
        options.add_experimental_option("prefs", {"intl.accept_languages": accept_languages})
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        if self.headless:
            options.add_argument("--headless=new")
        if self.chrome_binary is not None:
            options.binary_location = str(self.chrome_binary)
        self.driver = webdriver.Chrome(options=options)
        try:
            self.driver.execute_cdp_cmd("Network.enable", {
                "maxTotalBufferSize": 64 * 1024 * 1024,
                "maxResourceBufferSize": 16 * 1024 * 1024,
            })
            self.driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        except Exception:
            self.close()
            raise

    def capture(self, url: str, matches_url: Callable[[str], bool], quiet_period: float = 1.5) -> list[dict[str, Any]]:
        """To navigate to a URL and capture responses selected by the caller until traffic settles or times out."""

        self._validate_quiet_period(quiet_period)
        driver = self._get_driver()
        driver.get_log("performance")
        self._completed_requests.clear()
        driver.get(url)
        return self.capture_responses(matches_url, quiet_period)

    def capture_responses(
        self, 
        matches_url: Callable[[str], bool], 
        quiet_period: float = 1.5, 
        *, 
        required: bool = True,
        ) -> list[dict[str, Any]]:
        """To collect queued and new responses without navigating or discarding events between scrolls."""

        self._validate_quiet_period(quiet_period)
        driver = self._get_driver()
        pending: dict[str, dict[str, Any]] = {}
        responses: list[dict[str, Any]] = []
        failures: list[str] = []
        completed = self._completed_requests
        deadline = time.monotonic() + self.timeout
        last_activity = time.monotonic()

        while time.monotonic() < deadline:
            for entry in driver.get_log("performance"):
                message = json.loads(entry["message"])["message"]
                method = message.get("method")
                params = message.get("params", {})
                request_id = params.get("requestId")
                if request_id in completed:
                    continue
                if method == "Network.requestWillBeSent":
                    request_url = params["request"]["url"]
                    if matches_url(request_url):
                        pending[request_id] = {"request_id": request_id, "url": request_url, "status": None}
                        last_activity = time.monotonic()
                    elif request_id in pending:
                        pending.pop(request_id)
                        failures.append(f"Matched request redirected to {request_url}")
                elif method == "Network.responseReceived":
                    response = params["response"]
                    if matches_url(response["url"]):
                        pending[request_id] = {
                            "request_id": request_id, "url": response["url"], "status": response["status"],
                        }
                        last_activity = time.monotonic()
                elif method in ("Network.loadingFinished", "Network.loadingFailed") and request_id in pending:
                    response = pending.pop(request_id)
                    completed.add(request_id)
                    last_activity = time.monotonic()
                    if method == "Network.loadingFailed":
                        failures.append(f"{response['url']}: {params.get('errorText', 'Network loading failed')}")
                    elif response["status"] is None or not 200 <= response["status"] < 300:
                        failures.append(f"{response['url']}: HTTP {response['status']}")
                    else:
                        try:
                            response["body"] = self._get_response_body(request_id)
                            responses.append(response)
                        except (WebDriverException, ValueError, UnicodeError) as error:
                            failures.append(f"{response['url']}: could not read response body: {error}")

            idle_time = time.monotonic() - last_activity
            if (responses or failures) and not pending and idle_time >= quiet_period:
                break
            if not required and not responses and not failures and not pending and idle_time >= max(2, quiet_period):
                break
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))

        self._raise_if_blocked()
        if pending:
            raise TimeoutError(f"Matched responses did not finish within {self.timeout} seconds: {list(pending)}")
        if failures:
            raise RuntimeError("Response capture failed: " + "; ".join(failures))
        if required and not responses:
            raise TimeoutError(f"No matching response within {self.timeout} seconds; check consent or page layout")
        return responses

    @staticmethod
    def _validate_quiet_period(quiet_period: float) -> None:
        """To reject invalid response settling intervals before browser operations."""

        if not math.isfinite(quiet_period) or quiet_period < 0:
            raise ValueError("quiet_period must be a finite nonnegative number")

    def scroll_search(self, query: str, distance: int = 1000) -> bool:
        """To scroll the visible search feed and report whether its current bottom was reached."""

        self._raise_if_blocked()
        feed = WebDriverWait(self._get_driver(), self.timeout).until(
            lambda _: self._find_search_feed(query)
            )
        return self._get_driver().execute_script(
            "arguments[0].scrollTop += arguments[1];"
            "return arguments[0].scrollTop + arguments[0].clientHeight >= arguments[0].scrollHeight - 1;",
            feed, distance,
        )

    def _find_search_feed(self, query: str) -> WebElement | None:
        """To select one visible feed, using the query in its label only to resolve multiple candidates."""

        self._raise_if_blocked()
        feeds = [
            element 
            for element in self._get_driver().find_elements(By.CSS_SELECTOR, '[role="feed"]')
            if element.is_displayed()
            ]
        if len(feeds) > 1:
            feeds = [
                element 
                for element in feeds 
                if query in (element.get_attribute("aria-label") or "")
                ]
            if len(feeds) != 1:
                raise RuntimeError("Cannot uniquely identify the visible search feed")
        return feeds[0] if feeds else None

    def _raise_if_blocked(self) -> None:
        """To report visible CAPTCHA or Google blocking pages separately from an exhausted result list."""

        driver = self._get_driver()
        if "/sorry/" in driver.current_url or any(
            element.is_displayed() for element in driver.find_elements(
                By.CSS_SELECTOR, "form[action*='/sorry/'], iframe[src*='recaptcha']",
            )
        ):
            raise RuntimeError("Google blocked the request or requires CAPTCHA verification")

    def _get_response_body(self, request_id: str) -> str:
        """To read a completed CDP response body and decode Base64 when indicated."""

        result = self._get_driver().execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
        body = result["body"]
        if result.get("base64Encoded"):
            return base64.b64decode(body, validate=True).decode("utf-8")
        return body

    def _get_driver(self) -> webdriver.Chrome:
        """To require a started browser before navigating or reading CDP events."""

        if self.driver is None:
            raise RuntimeError("Browser has not started; call browser.start() first")
        return self.driver

    def close(self) -> None:
        """To release Chrome and allow cleanup before startup or after a previous close."""

        driver = self.driver
        self.driver = None
        if driver is not None:
            driver.quit()

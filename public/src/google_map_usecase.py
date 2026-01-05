import time, logging
import re
import pandas as pd
from selenium.webdriver.common.keys import Keys
from . import global_utils as gbut
logger = logging.getLogger("pipeline.google_map")

class Mixin:
    def scroll_and_results(self, worker, selector_elements, selector_scroll_area, target_count):
        # worker = SetupGoogleMap()
        cur_count = 0
        prev_count = 0
        elements = []
        scroll_area = worker.rt_session.find_element(sel=selector_scroll_area)
        if not scroll_area:
            raise RuntimeError("No element of scroll area.")

        # first count
        elements = worker.rt_session.find_elements(sel=selector_elements)
        if len(elements) >= target_count:
            final_els = elements[:target_count]
            gbut.log_print(logger, "Return - first count")
            gbut.log_print(logger, f"elements: {len(elements)}")
            gbut.log_print(logger, f"final_els: {len(final_els)}")
            return final_els
        
        cur_count = len(elements)
        gbut.log_print(logger, f"first elements: {cur_count}")
        gbut.log_print(logger, f"target_count: {target_count}")
        
        while cur_count < target_count:
            worker.rt_session.exe_script(
                script="arguments[0].scrollTop = arguments[0].scrollHeight;", 
                element=scroll_area
                )
            time.sleep(2)
            elements = worker.rt_session.find_elements(sel=selector_elements)
            cur_count = len(elements)
            gbut.log_print(logger, f"elements: {len(elements)}")
            gbut.log_print(logger, f"cur_count: {cur_count}")

            if cur_count > target_count:
                final_els = elements[:target_count]
                gbut.log_print(logger, "Break Loop - cur_count > target_count")
                gbut.log_print(logger, f"elements: {len(elements)}")
                gbut.log_print(logger, f"final_els: {len(final_els)}")
                break

            if cur_count == target_count:
                final_els = elements
                gbut.log_print(logger, "Break Loop - cur_count == target_count")
                gbut.log_print(logger, f"elements: {len(elements)}")
                gbut.log_print(logger, f"final_els: {len(final_els)}")
                break
            
            if cur_count == prev_count:
                final_els = elements
                gbut.log_print(logger, "Break Loop - cur_count == prev_count")
                gbut.log_print(logger, f"elements: {len(elements)}")
                gbut.log_print(logger, f"final_els: {len(final_els)}")
                break


            prev_count = cur_count

        return final_els

class GetResult(Mixin):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker 

    def run(self, ctx):
        # Unpack
        url = ctx.url
        num_target_search_results = ctx.num_target_search_results
        selector_search_box = ctx.selector_search_box
        keyword = ctx.keyword
        selector_cards = ctx.selector_cards
        selector_scroll_area_cards = ctx.selector_scroll_area_cards


        # Access
        self.worker.rt_session.access_url_selenium(url=url)

        # First fetch
        html = self.worker.rt_session.fetch_html()
        is_bot, _ = self.worker.bot_detection.is_bot_detection(html=html)
        if is_bot:
            raise RuntimeError("Bot detection happened")

        # Search
        serach_box = self.worker.rt_session.get_element(sel=selector_search_box)
        self.worker.rt_session.clear_element(element=serach_box)
        time.sleep(0.1)
        self.worker.rt_session.send_keys_to_element(element=serach_box, keyword=keyword)
        time.sleep(0.1)
        self.worker.rt_session.send_keys_to_element(element=serach_box, keyword=Keys.ENTER)
        
        # Check if diplayed cards
        _ = self.worker.rt_session.check_element(selector=selector_cards)

        # Get search results
        cards = self.scroll_and_results(
            worker=self.worker, 
            selector_elements=selector_cards, 
            selector_scroll_area=selector_scroll_area_cards, 
            target_count=num_target_search_results
            )
        gbut.log_print(logger, f"Card num: {len(cards)}")
        
        # For next step
        ctx.cards = cards

class EachCard(Mixin):
    def __init__(self, worker, session):
        super().__init__()
        self.worker = worker
        self.infra = session
    
    def run(self, ctx):
        # Unpack
        cards = ctx.cards
        

        save_dir = self.infra.set_save_dir_html()
        self.infra.ensure_dir(path=save_dir)
        for i, card in enumerate(cards, start=1):
            gbut.log_print(logger, f"Clicked Card - Overview {i}")
            save_path_overview = self.set_save_path_overview(i, save_dir)
            save_path_review = self.set_save_path_review(i, save_dir)

            # Click a card
            self.worker.rt_session.click_element(element=card)
            time.sleep(2)

            # Overview
            self.overview_process(ctx, save_path_overview)
            gbut.log_print(logger, f"[Saved] HTML_overview - {i:03}", path=save_path_overview)

            # Review
            self.review_process(i, ctx, save_path_review)
            gbut.log_print(logger, f"[Saved] HTML_review - {i:03}", path=save_path_review)
    
    def set_save_path_overview(self, i, save_dir):
        fn_overview_temp = self.infra.set_fn_overview_temp()
        fn_overview = fn_overview_temp.format(i=i)
        return save_dir / fn_overview

    def set_save_path_review(self, i, save_dir):
            fn_review_temp = self.infra.set_fn_review_temp()
            fn_review = fn_review_temp.format(i=i)
            return save_dir / fn_review

    def overview_process(self, ctx, save_path_overview):
        # Unpack
        selector_overview_tab = ctx.selector_overview_tab 


        # Check if displayed overview tab 
        _ = self.worker.rt_session.check_element(selector=selector_overview_tab)

        html = self.worker.rt_session.fetch_html()
        self.worker.rt_session.save(save_path_overview, html)

    def review_process(self, i, ctx, save_path_review):
        # Unpack
        num_target_review = ctx.num_target_review
        selector_review_tab = ctx.selector_review_tab 
        selector_reviews = ctx.selector_reviews 
        selector_scroll_area_reviews = ctx.selector_scroll_area_reviews 
        selector_button_review_detail = ctx.selector_button_review_detail 


        # Click review tab
        review_tab = self.worker.rt_session.find_element(sel=selector_review_tab)
        if not review_tab:
            html = ""
            self.worker.rt_session.save(save_path_review, html)
            gbut.log_print(logger, f"No review - {i}, Next")
            return
        self.worker.rt_session.click_element(element=review_tab)
        
        # Check if displayed review cards
        _ = self.worker.rt_session.check_element(selector=selector_reviews)
        gbut.log_print(logger, f"Clicked Tab - Review {i}")

        # Scroll and Get review cards
        review_elements = self.scroll_and_results(
            worker=self.worker, 
            selector_elements=selector_reviews, 
            selector_scroll_area=selector_scroll_area_reviews, 
            target_count=num_target_review
            )
        gbut.log_print(logger, f"Review num: {len(review_elements)}")

        # Expand each review
        for j, review in enumerate(review_elements, start=1):
            gbut.log_print(logger, f"Open detail - {j}")
            is_next = self._detail_process(review, selector_button_review_detail)
            if is_next:
                continue

        # Fetch HTML - review
        html = self.worker.rt_session.fetch_html()
        self.worker.rt_session.save(save_path_review, html)
        

    def _detail_process(self, review, selector_button_review_detail):
        # Get detail button in review card
        btn = self.worker.rt_session.find_element(
            sel=selector_button_review_detail, 
            el=review
            )
        
        if not btn:
            gbut.log_print(logger, "Not found detailed button")
            return True

        # Scroll to display button at center position
        self.worker.rt_session.exe_script(
            script="arguments[0].scrollIntoView({block: 'center'});",
            element=btn
            )
        time.sleep(0.7)
    
        # Click detail button
        self.worker.rt_session.click_element(element=btn)
        time.sleep(0.3)
        return False

class Extract:
    def __init__(self, session):
        self.infra = session

    def run(self, ctx):
        # Unpack
        selector_dict_overview = ctx.selector_dict_overview
        selector_dict_review = ctx.selector_dict_review
        index_order = ctx.index_order
        num_target_review = ctx.num_target_review


        # Get html list
        list_html_path_overview, list_html_path_review = self.get_list_html()
        save_path = self.set_save_path()

        # Check nums of html
        if not len(list_html_path_overview) == len(list_html_path_review):
            raise RuntimeError("Not match number of HTML: overview and review")
        
        data_whole_overview = self.extract_data(list_html_path_overview, selector_dict_overview, tab="overview")
        data_whole_review = self.extract_data(list_html_path_review, selector_dict_review, tab="review")

        index_order = self.create_index_col(index_order, num_target_review)

        vertical_dict = self.transpose_dataset(data_whole_overview, data_whole_review, index_order)

        df = (pd.DataFrame(
            vertical_dict,
            index=pd.CategoricalIndex(
                index_order,
                categories=index_order,
                ordered=True,
                name="type"
                ))
            .sort_index()
            .reset_index()
            )

        self.infra.save_data(save_path, df)
        gbut.log_print(logger, f"[Saved] Extracted data", path=save_path)

    def get_list_html(self):
        html_dir = self.infra.set_load_dir()
        list_html_path_overview = self.infra.list_files(target_dir=html_dir, kw="*_overview.html")
        list_html_path_review = self.infra.list_files(target_dir=html_dir, kw="*_review.html")
        return list_html_path_overview, list_html_path_review
        
    def set_save_path(self):
        save_dir_data = self.infra.set_save_dir_data()
        self.infra.ensure_dir(path=save_dir_data)
        fn_save_temp = self.infra.set_fn_save_temp()
        fn_save = fn_save_temp.format(
            site_name="google_map"
        )
        return save_dir_data / fn_save

    def extract_data(self, list_html, selector_dict, tab):
        data_whole = []
        for i, path_o in enumerate(list_html, start=1):
            sq = i
            # gbut.log_print(logger, f"sq: {i}", path_o=path_o)

            # Load HTML
            soup = self.infra.load_html_removed(filepath=path_o)
            gbut.log_print(logger, f"[Loaded] {path_o}")

            # gbut.log_print(logger, selector_dict)
            data = {"sq": sq}
            # Check if HTML is empty
            if not soup.select("body"):
                data["flag_extract"] = "skipped"
                for key in selector_dict:
                    data[key] = "skipped"
                data_whole.append(data)
                gbut.log_print(logger, f"No HTML, and Skipped - {sq}", data_whole=data_whole)
                continue

            # Extract
            data["flag_extract"] = "success"
            if tab == "overview":
                data = self._overview(selector_dict, soup, data)
            elif tab == "review":
                data = self._review(selector_dict, soup, data)
            # gbut.log_print(logger, data)
            
            data_whole.append(data)
            gbut.log_print(logger, f"{i} - Extract data")
        return data_whole

    def _overview(self, selector_dict, soup, data):
        for key, sel in selector_dict.items():
            val = ""
            if key == "link":
                el = self.infra.select_one_element(html=soup, selector=sel)
                val = el.get("href") if el else ""
            else:
                elements = self.infra.select_elements(html=soup, selector=sel)
                val = " ".join(el.get_text(strip=True) for el in elements)
            data[key] = val
        return data

    def _review(self, selector_dict, soup, data):
        for key, sel in selector_dict.items():
            if key == "each_rate":
                each_rate = self._each_rate(soup, selector_dict["each_rate"])
                data.update(each_rate)
            elif key == "rating_num":
                elements = self.infra.select_elements(html=soup, selector=sel)
                text = " ".join(el.get_text(strip=True) for el in elements)
                m = re.search(r"(\d[\d,]*)\s*件のクチコミ", text)
                if not m:
                    m = re.search(r"\((\d[\d,]*)\)", text)
                data[key] = int(m.group(1).replace(",", "")) if m else ""
            elif key == "rating":
                el = self.infra.select_one_element(html=soup, selector=sel)
                text = el.get_text(strip=True)
                data[key] = text
        data = self._comment(selector_dict, soup, data)
        return data

    def _comment(self, selector_dict, soup, data):
        elements = self.infra.select_elements(html=soup, selector=selector_dict["text_area"])
        i = 1
        for els in elements:
            el_text = self.infra.select_one_element(html=els, selector=selector_dict["review_text"])
            review_text = el_text.get_text(separator="\n", strip=True) if el_text else ""

            el_rubic = self.infra.select_one_element(html=els, selector=selector_dict["review_rubic"])
            review_rubic = el_rubic.get_text(separator="\n", strip=True) if el_rubic else ""

            if review_text or review_rubic:
                text = "\n".join([review_text, review_rubic])
                data[f"review_{i:02d}"] = text
                i +=1
                # gbut.log_print(logger, text)
        return data
    
    def _each_rate(self, soup, sel):
        rows = soup.select(sel)
        result = {}

        for tr in rows:
            aria = tr['aria-label']
            m = re.search(r'(\d+)\s*つ星、クチコミ\s*(\d+)\s*件', aria)
            if m:
                star = int(m.group(1))
                count = int(m.group(2))
                result[f"star_{star}"] = count
        return result
    
    def create_index_col(self, index_order, num_target_review):
        return (
            index_order
            + [f"star_{i}" for i in range(5, 0, -1)]
            + [f"review_{i:02d}" for i in range(1, num_target_review+1)]
        )
    
    def transpose_dataset(self, data_whole_overview, data_whole_review, index_order):
        vertical_dict = {}
        for ov, rv in zip(data_whole_overview, data_whole_review):
            rows = {}
            for k in index_order:
                rows[k] = rv.get(k, ov.get(k, ""))
            vertical_dict[f"shop_{rows['sq']}"] = rows
        return vertical_dict
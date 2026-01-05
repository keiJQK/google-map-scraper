import logging
from scraping.src.retrieve import worker_selenium as w_sel
from . import global_utils as gbut
from . import global_vars as gv
from . import google_map_infrastructure as inf
from . import google_map_usecase as uc
logger = logging.getLogger("pipeline.google_map")

# ---- DTO ----
class MapContext:
    def __init__(self, keyword, num_target_search_results, num_target_review):
        # Input
        self.keyword = keyword
        self.num_target_search_results = num_target_search_results
        self.num_target_review = num_target_review

        # For usecase: GetResult
        self.url = "https://www.google.co.jp/maps/"
        self.selector_cards = (
            "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde.ecceSd > "
            "div > "
            "div.Nv2PK"
            )
        self.selector_scroll_area_cards = (
            "div[role='main'] "
            "div[role='feed'][tabindex='-1']"
            )
        self.selector_search_box = (
            "form#XmI62e > "
            "input#searchboxinput"
            )

        # For usecase: EachCard
        self.selector_overview_tab = (
            "div.yx21af.lLU2pe > "
            "div.RWPxGd > "
            "button.hh2c6[aria-label*='概要']"
            )
        self.selector_review_tab = (
            "div.yx21af.lLU2pe > "
            "div.RWPxGd > "
            "button.hh2c6[aria-label*='クチコミ']"
            )
        self.selector_reviews = (
            "div.m6QErb.WNBkOb.XiKgde > "
            "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde > "
            "div.m6QErb.XiKgde > "
            "div.jftiEf.fontBodyMedium" 
        )
        self.selector_scroll_area_reviews = (
            "div.bJzME.Hu9e2e.tTVLSc > "
            "div.k7jAl.miFGmb.lJ3Kh > "
            "div.e07Vkf.kA9KIf > "
            "div.aIFcqe > "
            "div.m6QErb.WNBkOb.XiKgde > "
            "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde"
        )
        self.selector_button_review_detail = (
            "div.MyEned > "
            "span > "
            "button[aria-label='詳細']"
            )

        # For extract: Cleansing
        self.selector_dict_overview = {
            "name": "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde > div.TIHn2 > div.tAiQdd > div.lMbq3e > div > h1.DUwDvf.lfPIob"
            ,
            "address":"button.CsEnBe[data-item-id='address'] div.rogA2c",
            "location": "button.CsEnBe[data-item-id='locatedin'] div.rogA2c",
            "link": "a.CsEnBe[data-item-id='authority']",
            "tel": "button.CsEnBe[data-item-id*='phone:'] div.rogA2c",
            "plus_code": "button.CsEnBe[data-item-id='oloc'] div.rogA2c"
            }
        self.selector_dict_review = {
            "rating": "div.Bd93Zb > div > div.fontDisplayLarge",
            "rating_num": "div.Bd93Zb > div > div.fontBodySmall",
            "each_rate": "div.Bd93Zb > div.ExlQHd > table > tbody > tr.BHOKXe[aria-label]", 
            "text_area": "div.m6QErb.XiKgde > div.jftiEf.fontBodyMedium div.GHT2ce",
            "review_text": "div.MyEned > span.wiI7pd",
            "review_rubic": "div[jslog='127691']",
        }
        self.index_order = ["sq", "flag_extract", "name", "address", "location", "link", "tel", "plus_code", "rating", "rating_num"]

        # Defined later
        self.cards = None


# runner - fetch HTML        
class GoogleMap:
    def __init__(self, worker, session):
        self.worker = worker
        self.steps = [
            uc.GetResult(worker=worker),
            uc.EachCard(worker=worker, session=session),
            uc.Extract(session=session)
        ]

    def run(self, ctx):
        try:
            for step in self.steps:
                step.run(ctx=ctx)
        except:
            raise
        finally:
            self.worker.rt_session.worker_end_process()

def temporary_setup():
    # NOTE:
    # This repository does NOT include the Selenium worker implementation.
    # Replace this function to create and return your own SetupGoogleMap worker.
    # See: HOW_TO_RUN.md#required-worker-contract-selenium
    raise NotImplementedError(
        "Selenium worker is not included in this repository.\n"
        "Provide your own SetupGoogleMap worker here.\n"
        "See HOW_TO_RUN.md#required-worker-contract-selenium"
    )


if __name__ == "__main__":
    try:
        logger = gbut.setup_logger(fn="gmap", logger_name="pipeline.google_map")

        worker = temporary_setup()
        worker.run()

        ctx = MapContext(
            keyword="bar",
            num_target_search_results=5, 
            num_target_review=10
            )
        
        infra = inf.MapInfra()
        map = GoogleMap(worker=worker, session=infra)
        map.run(ctx=ctx)
    except Exception as e:
        gbut.logging_error(logger=logger, src_dir=gv.LOG_DIR, e=e)

    gbut.log_print(logger, "--------- End ---------")
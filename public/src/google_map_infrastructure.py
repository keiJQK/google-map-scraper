import logging
from pathlib import Path
from bs4 import BeautifulSoup
from . import global_utils as gbut
from . import global_vars as gv
logger = logging.getLogger("pipeline.google_map")

class MapInfra:
    def ensure_dir(self, path):
        path.mkdir(parents=True, exist_ok=True)

    # Fetch HTML
    def set_fn_overview_temp(self):
        return  "maps_{i:03}_overview.html"
    
    def set_fn_review_temp(self):
        return  "maps_{i:03}_review.html"

    def set_save_dir_html(self):
        return gv.HTML_DIR
    
    def save_html(self, path, html):
        gbut.save_html(path, html)

    # Extract data
    def set_load_dir(self):
        return gv.HTML_DIR
    
    def set_save_dir_data(self):
        return gv.CSV_DIR

    def set_fn_save_temp(self):
        return "output_{site_name}.csv"

    def list_files(self, target_dir, kw):
        return list(target_dir.glob(kw))

    def load_html_removed(self, filepath):
        load_data = gbut.load_html(filepath)
        soup = self._remove_text(BeautifulSoup(load_data, "lxml"))  
        return soup

    def _remove_text(self, soup):
        for tag_name in ["script", "style"]:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        return soup     

    def select_one_element(self, html, selector):
        return html.select_one(selector)
    
    def select_elements(self, html, selector):
        return html.select(selector)
    
    def save_data(self, path, df):
        gbut.save_csv(path, df)
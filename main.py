import logging

# Set up logging
logging.basicConfig(
    filename="parser.log",
    filemode="w",
    encoding="utf-8",
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s: %(message)s")

import pickle
from os.path import exists
from os import mkdir
from urllib.parse import urljoin
import re

import openpyxl
import requests
from bs4 import BeautifulSoup as BS
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def chunk_generator(data: list, chunk_size=1000):
    """ Yields chunks of data with a maximum size of 1000"""
    for i in range(0, len(data), chunk_size):
        yield data[i:i+chunk_size]
        
        
def save_progress(data: list):
    logging.info("Saving all visited links...")
    with open("data.pkl", "wb") as f:
        for chunk in chunk_generator(data):
            pickle.dump(chunk, f)
            
def load_progress() -> list:
    logging.info("Loading from where we left off...")
    data = list()
    
    if not exists("data.pkl"):
        logging.warning("data.pkl not found")
        return data
    
    with open("data.pkl", "rb") as f:
        while True:
            try:
                chunk = pickle.load(f)
                data.append(chunk)
            except EOFError:
                return data


def is404(url: str):
    """Checks whether requested URL returns 404 page

    Args:
        url (str): URL of page

    Returns:
        True (bool): Requested URL returned 404 \n
        False (bool): Requested URL loaded normally \n
        str: Request resulted in a different error code
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return True
        # any other type of error
        print(f"Requested URL returned:\n {e}")
        return e
    except requests.exceptions.RequestException as e:
        print(f"Requested URL returned:\n {e}")
        return e
    
    return False

def create_workbook(workbook: openpyxl.Workbook):
    """Creates a xlsx file

    Args:
        workbook (openpyxl.Workbook): Openpyxl driver
    """
    headers = [
            "images",
            "Название производителя",
            "Страна",
            "Номер детали",
            "Название детали",
            "Развернутое описание детали",
            "category"
        ]

    page = workbook.active
    page.append(headers)
    workbook.save("kitaec.xlsx")
    logging.info("New Workbook created")
    
def open_workbook(file: str):
    """Opens xlsx file

    Args:
        file (str): File location

    Returns:
        Workbook: openpyxl driver
    """
    workbook = openpyxl.open(file)
    logging.info("Opened existing Workbook")
    
    return workbook

def workbook_write(workbook: openpyxl.Workbook, data: list):
    """Writes into xlsx file

    Args:
        workbook (openpyxl.Workbook): Openpyxl driver\n
        data (list): Data to write into the document
    """
    page = workbook.active
    page.append(data)
    workbook.save("kitaec.xlsx")
    logging.info(f"Saved {data} into the Workbook")

def wait_for(driver: webdriver.Chrome, timeout: int, by: By, value: str):
    try:
        element = WebDriverWait(driver=driver, timeout=timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except TimeoutException:
        logging.warning(f"Couldn't find elements {by} with name of {value} at {driver.current_url}. Skipping...")
        return None

    return True

def connect_to(url: str, driver: webdriver.Chrome, product_page: bool = False):
    """Connects to given URL and returns page source

    Args:
        url (str): URL to connect to\n
        driver (webdriver.Chrome): Chrome webdriver

    Returns:
        str: Page source of the URL
        None: Page returned an error
    """
    page_status = is404(url)
    
    if page_status:
        logging.warning("Page returned 404. Skipping...")
        return None
    if type(page_status) == str:
        logging.error(f"Page returned an error {page_status}. Skipping...")
        return None
    
    driver.get(url)
    if product_page:
        if wait_for(driver, 5, By.CLASS_NAME, "kc__code") == None:
            return None
    else:
        if wait_for(driver, 5, By.CLASS_NAME, "kc__card--inner") == None:
            return None
    
    return driver.page_source

def check_for_visiting(url: str):
    visited = False
    for chunk in visited_links:
        if url in chunk:
            visited = True
            break
    
    return visited

def get_sitemap_links(file: str):
    """Extracts links from a sitemap

    Args:
        file (str): XML file to extract from

    Returns:
        list: List of all links from the sitemap
    """
    with open(file, "r") as f:
        soup = BS(f, "xml")
    
    links = []
    
    for link in soup.find_all("loc"):
        linkstr = link.getText("", True)
        links.append(linkstr)
    
    return links

def get_button(driver: webdriver.Chrome, by_parent: By, value_parent: str, by_child: By, value_child: str, multiple: bool = False):
    """Returns either the first found button or multiples of it in parent element

    Args:
        driver (webdriver.Chrome): Chrome driver\n
        by_parent (By): Parent attribute\n
        value_parent (str): Parent value\n
        by_child (By): Child attribute\n
        value_child (str): Child value\n
        multiple (bool, optional): Returns all found buttons if True. Defaults to False.

    Returns:
        List(WebElement) | WebElement: Found button(s)
    """
    container = driver.find_element(by_parent, value_parent)
    children = container.find_elements(by_child, value_child)
    
    if multiple:
        return children
    
    return children[0]

def get_pages_amount(driver: webdriver.Chrome):
    button = get_button(driver, By.CLASS_NAME, "kc__pagination", By.CLASS_NAME, "item", True)
    
    return int(button[-2].text)

def open_next_page(driver: webdriver.Chrome):
    """Opens next page by clicking the arrow button

    Args:
        driver (webdriver.Chrome): Chrome driver
    """
    button = get_button(driver, By.CLASS_NAME, "kc__pagination", By.CLASS_NAME, "item", True)
    button[-1].click()
    
def save_product_details(soup: BS, workbook: openpyxl.Workbook, driver: webdriver.Chrome):
    product_title = soup.find("div", class_ = "kc__pagetitle--wrap")
    product_name = product_title.find("h1").text
    
    #i fucking hate how getting product location works so much
    product_location_raw = product_title.find_all("a")[1:]
    product_location_raw_text = list()
    for location in product_location_raw:
        # Thanks, Stackoverflow: https://stackoverflow.com/a/14824444
        p = re.compile('\\s*(.*\\S)?\\s*')
        text = p.search(location.text)
        
        product_location_raw_text.append(text.group(1))
    product_location_finish = "/".join(product_location_raw_text)
    
    product_code = soup.find_all("div", class_ = "kc__code")[-1].text.replace("Артикул: ", "")
    
    product_features = soup.find("div", class_ = "kc__product--features")
    product_features_spans = product_features.find_all("span")
    product_manufacturer = product_features_spans[0].text
    
    product_country = product_features_spans[2].text
    
    workbook_write(workbook, [
        f"{product_code}.png",
        product_manufacturer,
        product_country,
        product_code,
        product_name,
        product_name,
        product_location_finish])
    
    save_product_image(f"{product_code}.png", driver)
    
def save_product_image(filename: str, driver: webdriver.Chrome):
    if not exists("./images"):
        mkdir("./images")
    
    with open("./images/" + filename, "wb") as f:
        carousel = driver.find_element(By.CLASS_NAME, "carousel__slide")
        image = carousel.find_element(By.CLASS_NAME, "kc__real-image")
        f.write(image.screenshot_as_png)
        logging.info(f"Saved image: {'./images' + filename}")
    
def process_product_pages(driver: webdriver.Chrome, workbook: openpyxl.Workbook):
    base_link = "https://kitaec.ua"
    soup = BS(driver.page_source, "html.parser")
    cards = soup.find_all("div", class_ = "kc__card--inner")
    
    # I'm writing this while being intoxicated with energy drinks,
    # on at least 3 hours of sleep and a mild hangover.
    # I feel like im gonna regret this later
    for card in cards:
        absolute_link = card.find("a")["href"]
        link = urljoin(base_link, absolute_link)
        if check_for_visiting(link):
            continue
        
        visited_links.append(link)
        page = connect_to(link, driver, True)
        if page == None:
            continue # skip ads pages
        
        soup = BS(page, "html.parser")
        save_product_details(soup, workbook, driver)
        
        
        save_progress(visited_links)
        
def parse(driver: webdriver.Chrome, workbook: openpyxl.Workbook):
    urls = get_sitemap_links("sitemap-category.xml")
    for url in urls:
        if check_for_visiting(url):
            continue
               
        visited_links.append(url)
        
        page = connect_to(url, driver)
        
        if page == None:
            save_progress(visited_links)
            continue
        
        for i in range(get_pages_amount(driver)):
            process_product_pages(driver, workbook)
            open_next_page(driver)
        
        save_progress(visited_links)
        
        
if __name__ == "__main__":
    DRIVER_PATH = "./chromedriver.exe"
    visited_links = load_progress()
    
    #Create workbook instance
    logging.info("Loading workbook")
    workbook = openpyxl.Workbook()
    
    if not exists("./kitaec.xlsx"):
        create_workbook(workbook)
    else:
        workbook = open_workbook("kitaec.xlsx")
    
    # Create browser instance
    # We want to avoid getting detected
    # and this is the best option i have found.
    # Chromedriver provides devtoolkit commands with Selenium
    # that allow to to achieve what i want... or at least i hope it does
    logging.info("Loading browser instance")
    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
    options.add_argument("log-level=3")
    driver = webdriver.Chrome(options=options, executable_path=DRIVER_PATH)
    
    logging.info("Starting parse")
    parse(driver, workbook)
    
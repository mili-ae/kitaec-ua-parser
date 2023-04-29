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
                print(data)
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
            "Номер детали",
            "Название детали",
            "Развернутое описание детали",
            "category",
            "@Длина кабеля питания см",
            "@Выход",
            "@Вход",
            "@Размер",
            "@Вес",
            "@Состав",
            "@Размер удерживаемого устройства",
            "@Особенности",
            "@Дополнительные аксессуары",
            "@Напряжение питания",
            "@размеры",
            "@Дисплей",
            "@Память",
            "@Источник питания",
            "@Угол обзора камеры"
        ]

    page = workbook.active
    page.append(headers)
    workbook.save("kitaec.xlsx")
    print("New workbook created")
    
def open_workbook(file: str):
    """Opens xlsx file

    Args:
        file (str): File location

    Returns:
        Workbook: openpyxl driver
    """
    workbook = openpyxl.open(file)
    print("Opened existing workbook")
    
    return workbook

def workbook_write(workbook: openpyxl.Workbook):
    pass

def connect_to(url: str, driver: webdriver.Chrome):
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
    try:
        element = WebDriverWait(driver=driver, timeout=5).until(
            EC.presence_of_element_located((By.CLASS_NAME, "kc__card--inner"))
        )
    except TimeoutException:
        logging.info(f"Couldn't find elements with class name of kc__card--inner at {url}. Skipping...")
        return None
    
    return driver.page_source

def get_sitemap_links(file: str):
    """Extracts links from a sitemap

    Args:
        file (str): XML file to extract from

    Returns:
        list: List of all links from the sitemap
    """
    with open(file, "r") as f:
        soup = BS(f)
    
    links = []
    
    for link in soup.find_all("loc"):
        linkstr = link.getText("", True)
        links.append(linkstr)
    
    return links

def parse(driver: webdriver.Chrome):
    urls = get_sitemap_links("sitemap-category.xml")
    
    # I hate how this litle bit of check works.
    # Might rewrite it later if i won't forget about it or get lazy 
    for url in urls:
        visited = False
        for chunk in visited_links:
            if url in chunk:
                visited = True
                break
        if visited:
            continue   
               
        visited_links.append(url)
        
        page = connect_to(url, driver)
        
        if page == None:
            save_progress(visited_links)
            continue
        
        
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
    logging.info("Loading browser instance")
    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options, executable_path=DRIVER_PATH)
    
    logging.info("Starting parse")
    parse(driver)
    
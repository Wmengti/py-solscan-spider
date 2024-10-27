import time
import random
from datetime import datetime
from urllib.parse import urljoin

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import TimeoutException,NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

from core.config import settings
from core.logger import get_logger
from schemas.parse_schemas import SolscanResult
from services.google_sheets import GoogleSheets

logger = get_logger(__name__)


class SolscanParser:
    def __init__(self, hashes: list[str]):
        # self.google_sheets = GoogleSheets()
        self.url = settings.main_url
        self.hashes = hashes
        self.driver = None

    def __enter__(self):
        logger.info("Entering to the browser...")

        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument("--disable-popup-blocking")
        # chrome_options.add_argument("--headless")
         # Rotate user agents
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
            # Add more user agents as needed
        ]
        chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")

        self.driver = uc.Chrome(use_subprocess=True, options=chrome_options)

        return self

    def __exit__(self, exc_type, exc_value, _):
        logger.info("Exiting from the browser...")
        if exc_type:
            logger.error(f"An exception occurred: {exc_value}")

        if self.driver:
            self.driver.close()

        return False

    def proccess_sol(
        self, result: SolscanResult, elem: WebElement
    ) -> SolscanResult:
        logger.debug(f"Trying process SOL for {result.hash}: {elem.text}")
        if elem:
            row_text = elem.text
            sol_balance = row_text.split(" ")[0].strip()
            result.sol_count = sol_balance

        return result

    def proccess_spl(
        self, result: SolscanResult, elem: WebElement
    ) -> SolscanResult:
        logger.info(f"Trying process Token for {result.hash}: {elem.text}")
        if elem:
            row_text = elem.text
            spl_count, spl_usd = row_text.split("\n")
        #     spl_count = spl_count.split(" ")[0]
        #     spl_usd = spl_usd.replace("(", "").replace(")", "").replace("$", "")

        #     result.spl_count = spl_count
        #     result.spl_usd = spl_usd

        return result


    def extract_time_hover_text(self,  elem: WebElement, driver) -> str:
        # Locate the <div> element with the specified class
        time_hover_element = elem.find_element(By.XPATH, ".//div[contains(@class, 'not-italic')]")
                
        # Create an ActionChains object
        actions = ActionChains(driver)
    
        # Move to the element to trigger the hover effect
        actions.move_to_element(time_hover_element).perform()
        
        # Wait for the hover text to appear
        new_element = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, ".//div[@data-side='top']"))
        )
        
        # Extract the text from the new element if needed
        hover_text = new_element.text
        return hover_text

    def extract_fields_from_table(
        self, result: SolscanResult, elem: WebElement,driver) -> SolscanResult:
    
        # Locate all rows within the table body
        rows = elem.find_elements(By.TAG_NAME, "tr")

        # Iterate over each row and extract fields
        for row in rows:
            # Extract each field from the row
            
            try:
            
                signature = row.find_element(By.XPATH, ".//a[contains(@href, '/tx/')]").text
                time = self.extract_time_hover_text(row, driver)
                action = row.find_element(By.XPATH, ".//div[contains(@class, 'uppercase')]").text
                
                account_elements = row.find_elements(By.XPATH, ".//a[contains(@href, '/account/')]")
                if len(account_elements) >= 2:
                    from_account_href = account_elements[0].get_attribute("href")
                    from_account = from_account_href.split("/")[-1]
                    
                    to_account_href = account_elements[1].get_attribute("href")
                    to_account = to_account_href.split("/")[-1]
                change_amount = row.find_element(By.XPATH, ".//td/div[contains(@class, 'not-italic')]").text
                token = row.find_element(By.XPATH, ".//a[contains(@href, '/token/')]").text
            # # Print or store the extracted data
                result.signature=signature
                result.time=time
                result.action=action
                result.from_account=from_account
                result.to_account=to_account
                result.change_amount=change_amount
                result.token=token
                   
            except (TimeoutException, NoSuchElementException):
                print("Hover text did not appear or element not found.")   
        return result

    def parse_token_transfer(self, result: SolscanResult, driver) -> SolscanResult:
        logger.info("Trying to parse token transfer")

        while True:
            try:
                # Wait for the table body to be present
                token_transfer_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//*[@id='radix-:r6:-content-default']/div/div[2]/div/div/div/div/table/tbody"
                        )
                    )
                )

                # Extract fields from the current page's table
                result = self.extract_fields_from_table(result, token_transfer_element, driver)

                # Locate the 'Next' button and check if it's enabled
                next_button = driver.find_element(By.XPATH, "//button[span[@aria-label='right']]")
                
                # Check if the 'Next' button is disabled
                button_classes = next_button.get_attribute("class")
                if "disabled" in button_classes and button_classes.strip().endswith("disabled"):
                    logger.info("No more pages to process.")
                    break

                # Scroll the button into view
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)

                # Use JavaScript to click the 'Next' button
                driver.execute_script("arguments[0].click();", next_button)

                # Wait for the next page to load
                WebDriverWait(driver, 10).until(
                    EC.staleness_of(token_transfer_element)
                )
            except (NoSuchElementException, TimeoutException) as e:
                logger.error(f"An exception occurred: {e}")
                break
            except Exception as e:
                logger.error(f"An unexpected exception occurred: {e}")
                break

        return result


    def fix_cf_just_moment(self, url: str, driver):
        # Fix CF `Just moment...` loading
        driver.execute_script(f"window.open('{url}', '_blank')")
        driver.switch_to.window(driver.window_handles[1])
        time.sleep(3)
        driver.close()

    def get_parse_result(self, hash: str) -> SolscanResult:
        if not self.driver:
            msg = "Please use context for the `SolscanParser`"
            logger.critical(msg)
            raise ValueError(msg)

        result = SolscanResult(date=datetime.now(), hash=hash)
        url = urljoin(self.url, hash)

        driver = self.driver
        driver.get(url)
        time.sleep(10)
     
        if "STACKS (STACKS)" not in driver.title:
            logger.error(f"Page title does not match for {hash}")
            return result

        self.fix_cf_just_moment(url, driver)
        driver.switch_to.window(driver.window_handles[0])


        # try:
        result = self.parse_token_transfer(result, driver)
            # result = self.parse_spl_values(result, driver)
        # except TimeoutException:
        #     logger.info(f"Can't found SQL Balance or Token values: {result.hash}")
        #     pass

        return result

    def process_hashes(self):
        for hash in self.hashes:
            parse_result = self.get_parse_result(hash)
            print(parse_result)
            # self.google_sheets.manage_spreadsheet(parse_result)



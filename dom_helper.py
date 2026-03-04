"""
Browser Pilot - DOM Helper
Unified element finding and interaction utilities.
"""
import time
import random
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

log = logging.getLogger("browser-pilot.dom")


# ─── Element Finding ───

BY_MAP = {
    "text": None,  # Special handling
    "class": By.CLASS_NAME,
    "id": By.ID,
    "name": By.NAME,
    "tag": By.TAG_NAME,
    "xpath": By.XPATH,
    "css": By.CSS_SELECTOR,
}


def find_element(driver, by_type, value, timeout=10, wait_visible=True):
    """
    Find a single element using various locator strategies.
    
    Args:
        driver: Selenium WebDriver
        by_type: One of "text", "class", "id", "name", "tag", "xpath", "css"
        value: The locator value
        timeout: Wait timeout in seconds
        wait_visible: Wait for element to be visible (not just present)
    
    Returns:
        WebElement or None if not found
    """
    try:
        if by_type == "text":
            # Find by text content (partial match)
            xpath = f"//*[contains(text(), '{value}')]"
            by = By.XPATH
            locator = xpath
        elif by_type in BY_MAP:
            by = BY_MAP[by_type]
            locator = value
        else:
            # Default to CSS selector
            by = By.CSS_SELECTOR
            locator = value
        
        wait = WebDriverWait(driver, timeout)
        if wait_visible:
            element = wait.until(EC.visibility_of_element_located((by, locator)))
        else:
            element = wait.until(EC.presence_of_element_located((by, locator)))
        
        return element
    except TimeoutException:
        log.warning(f"Element not found: {by_type}='{value}' within {timeout}s")
        return None
    except Exception as e:
        log.warning(f"Error finding element: {e}")
        return None


def find_elements(driver, by_type, value, timeout=10):
    """
    Find multiple elements using various locator strategies.
    
    Args:
        driver: Selenium WebDriver
        by_type: One of "text", "class", "id", "name", "tag", "xpath", "css"
        value: The locator value
        timeout: Wait timeout in seconds
    
    Returns:
        List of WebElements (empty if none found)
    """
    try:
        if by_type == "text":
            xpath = f"//*[contains(text(), '{value}')]"
            by = By.XPATH
            locator = xpath
        elif by_type in BY_MAP:
            by = BY_MAP[by_type]
            locator = value
        else:
            by = By.CSS_SELECTOR
            locator = value
        
        # Wait for at least one element
        wait = WebDriverWait(driver, timeout)
        wait.until(EC.presence_of_element_located((by, locator)))
        
        return driver.find_elements(by, locator)
    except TimeoutException:
        return []
    except Exception as e:
        log.warning(f"Error finding elements: {e}")
        return []


def find_element_smart(driver, selector, timeout=10):
    """
    Smart element finding - auto-detect selector type.
    
    Args:
        selector: Can be:
            - XPath starting with "//" or "("
            - CSS selector (default)
            - "#id" for ID
            - ".class" for class name
            - "tag" for tag name (if single word with no special chars)
    
    Returns:
        WebElement or None
    """
    if selector.startswith("//") or selector.startswith("("):
        return find_element(driver, "xpath", selector, timeout)
    elif selector.startswith("#"):
        return find_element(driver, "id", selector[1:], timeout)
    elif selector.startswith(".") and " " not in selector:
        return find_element(driver, "class", selector[1:], timeout)
    else:
        return find_element(driver, "css", selector, timeout)


# ─── Element Actions ───

def click_element(driver, element, double_click=False):
    """Click an element, optionally double-click."""
    actions = ActionChains(driver)
    if double_click:
        actions.double_click(element)
    else:
        actions.click(element)
    actions.perform()


def type_text(driver, element, text, clear_first=True, human_like=False):
    """
    Type text into an element.
    
    Args:
        driver: Selenium WebDriver
        element: Target WebElement
        text: Text to type
        clear_first: Clear existing content before typing
        human_like: Type with random delays between characters
    """
    if clear_first:
        element.clear()
        time.sleep(0.2)
    
    if human_like:
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
    else:
        element.send_keys(text)


def hold_element(driver, element, duration):
    """
    Press and hold an element for a specified duration.
    
    Args:
        driver: Selenium WebDriver
        element: Target WebElement
        duration: Duration in seconds to hold
    """
    actions = ActionChains(driver)
    actions.click_and_hold(element)
    actions.perform()
    
    time.sleep(duration)
    
    actions = ActionChains(driver)
    actions.release()
    actions.perform()


def hover_element(driver, element, duration=0.5):
    """Hover over an element."""
    actions = ActionChains(driver)
    actions.move_to_element(element)
    actions.perform()
    time.sleep(duration)


def drag_element(driver, element, offset_x=0, offset_y=0, to_element=None, human_like=True):
    """
    Drag an element by offset or to another element.
    
    Args:
        driver: Selenium WebDriver
        element: Source element to drag
        offset_x, offset_y: Pixel offsets to drag by
        to_element: Target element to drag to (overrides offsets)
        human_like: Use human-like mouse movement
    """
    if to_element:
        # Drag to another element
        if human_like:
            _drag_human_like(driver, element, to_element=to_element)
        else:
            actions = ActionChains(driver)
            actions.drag_and_drop(element, to_element)
            actions.perform()
    else:
        # Drag by offset
        if human_like:
            _drag_human_like(driver, element, offset_x=offset_x, offset_y=offset_y)
        else:
            actions = ActionChains(driver)
            actions.drag_and_drop_by_offset(element, offset_x, offset_y)
            actions.perform()


def _drag_human_like(driver, element, offset_x=0, offset_y=0, to_element=None):
    """
    Perform a human-like drag with acceleration/deceleration.
    Used for slider CAPTCHAs to avoid detection.
    """
    actions = ActionChains(driver)
    
    # Click and hold
    actions.click_and_hold(element)
    actions.perform()
    time.sleep(random.uniform(0.1, 0.2))
    
    # Calculate target position
    if to_element:
        # Get positions
        src = element.location
        dst = to_element.location
        offset_x = dst["x"] - src["x"]
        offset_y = dst["y"] - src["y"]
    
    # Generate human-like trajectory
    # Fast start, slow finish
    total_distance = offset_x
    current = 0
    steps = random.randint(15, 25)
    
    for i in range(steps):
        # Easing function: fast at start, slow at end
        progress = (i + 1) / steps
        # Ease-out cubic
        eased = 1 - pow(1 - progress, 3)
        target = int(total_distance * eased)
        
        move = target - current
        if move > 0:
            # Add small random vertical movement
            y_jitter = random.randint(-2, 2)
            
            actions = ActionChains(driver)
            actions.move_by_offset(move, y_jitter)
            actions.perform()
            
            current = target
            time.sleep(random.uniform(0.01, 0.03))
    
    # Small pause before release
    time.sleep(random.uniform(0.1, 0.3))
    
    # Release
    actions = ActionChains(driver)
    actions.release()
    actions.perform()


def scroll_page(driver, direction="down", amount=500):
    """
    Scroll the page.
    
    Args:
        driver: Selenium WebDriver
        direction: "up" or "down"
        amount: Pixels to scroll
    """
    if direction == "up":
        amount = -amount
    
    driver.execute_script(f"window.scrollBy(0, {amount});")


def scroll_to_element(driver, element):
    """Scroll an element into view."""
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)


# ─── Element Info ───

def get_element_info(element):
    """
    Get information about an element.
    
    Returns:
        Dict with element properties
    """
    return {
        "tag": element.tag_name,
        "text": element.text[:200] if element.text else "",
        "id": element.get_attribute("id"),
        "class": element.get_attribute("class"),
        "name": element.get_attribute("name"),
        "href": element.get_attribute("href"),
        "src": element.get_attribute("src"),
        "value": element.get_attribute("value"),
        "is_displayed": element.is_displayed(),
        "is_enabled": element.is_enabled(),
        "location": element.location,
        "size": element.size,
    }


def wait_for_element_gone(driver, by_type, value, timeout=30):
    """Wait for an element to disappear from the page."""
    try:
        if by_type == "text":
            xpath = f"//*[contains(text(), '{value}')]"
            by = By.XPATH
            locator = xpath
        elif by_type in BY_MAP:
            by = BY_MAP[by_type]
            locator = value
        else:
            by = By.CSS_SELECTOR
            locator = value
        
        wait = WebDriverWait(driver, timeout)
        wait.until(EC.invisibility_of_element_located((by, locator)))
        return True
    except TimeoutException:
        return False

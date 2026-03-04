"""
Browser Pilot - CAPTCHA Solver
Image CAPTCHA recognition using ddddocr and slider CAPTCHA automation.
"""
import base64
import io
import logging
import math
import random
import time
from typing import Optional, Tuple, List

try:
    import ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    DDDDOCR_AVAILABLE = False

try:
    from PIL import Image
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

log = logging.getLogger("browser-pilot")


class CaptchaSolver:
    """CAPTCHA solving utilities."""
    
    def __init__(self, api_key: Optional[str] = None, api_provider: str = "2captcha"):
        """
        Initialize CAPTCHA solver.
        
        Args:
            api_key: API key for fallback service (2captcha/anticaptcha)
            api_provider: API provider name (2captcha, anticaptcha)
        """
        self.api_key = api_key
        self.api_provider = api_provider
        self._ocr = None
        self._det = None
    
    @property
    def ocr(self):
        """Lazy load OCR model."""
        if self._ocr is None and DDDDOCR_AVAILABLE:
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr
    
    @property
    def det(self):
        """Lazy load detection model for slider gaps."""
        if self._det is None and DDDDOCR_AVAILABLE:
            self._det = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
        return self._det
    
    def recognize_image(self, image_data: bytes) -> dict:
        """
        Recognize text from image CAPTCHA.
        
        Args:
            image_data: Image bytes (PNG/JPEG)
        
        Returns:
            dict: {"success": bool, "text": str, "method": str}
        """
        # Try local OCR first
        if self.ocr:
            try:
                text = self.ocr.classification(image_data)
                if text:
                    return {"success": True, "text": text, "method": "ddddocr"}
            except Exception as e:
                log.warning(f"ddddocr recognition failed: {e}")
        
        # Fallback to API
        if self.api_key:
            result = self._call_api_ocr(image_data)
            if result["success"]:
                return result
        
        return {"success": False, "text": "", "method": "none"}
    
    def recognize_image_from_element(self, driver, element) -> dict:
        """
        Recognize CAPTCHA from a Selenium element.
        
        Args:
            driver: WebDriver instance
            element: Selenium element containing CAPTCHA image
        
        Returns:
            dict: {"success": bool, "text": str, "method": str}
        """
        try:
            # Get image as base64 from img element or screenshot
            tag_name = element.tag_name.lower()
            
            if tag_name == "img":
                # Try to get src attribute
                src = element.get_attribute("src")
                if src and src.startswith("data:image"):
                    # Base64 embedded image
                    image_data = base64.b64decode(src.split(",")[1])
                else:
                    # Take screenshot of element
                    image_data = element.screenshot_as_png
            else:
                # Screenshot element
                image_data = element.screenshot_as_png
            
            return self.recognize_image(image_data)
            
        except Exception as e:
            log.error(f"Failed to get CAPTCHA image: {e}")
            return {"success": False, "text": "", "method": "error"}
    
    def recognize_image_from_url(self, url: str) -> dict:
        """
        Recognize CAPTCHA from image URL.
        
        Args:
            url: Image URL
        
        Returns:
            dict: {"success": bool, "text": str, "method": str}
        """
        import requests
        
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return self.recognize_image(resp.content)
        except Exception as e:
            log.error(f"Failed to fetch CAPTCHA image: {e}")
            return {"success": False, "text": "", "method": "error"}
    
    def find_slider_gap(self, background_image: bytes, slider_image: bytes = None) -> dict:
        """
        Find the gap position in slider CAPTCHA.
        
        Args:
            background_image: Background image bytes (with gap)
            slider_image: Slider piece image bytes (optional)
        
        Returns:
            dict: {"success": bool, "x": int, "y": int, "method": str}
        """
        if not CV2_AVAILABLE:
            return {"success": False, "x": 0, "y": 0, "method": "cv2_not_available"}
        
        try:
            # Method 1: Edge detection for gap
            bg_array = np.frombuffer(background_image, np.uint8)
            bg_img = cv2.imdecode(bg_array, cv2.IMREAD_COLOR)
            
            # Convert to grayscale
            gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
            
            # Edge detection
            edges = cv2.Canny(gray, 100, 200)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Find the most likely gap (usually a rectangle)
            best_x, best_y = 0, 0
            best_area = 0
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                
                # Gap is usually square-ish and not too small
                if 30 < w < 100 and 30 < h < 100 and 0.7 < w/h < 1.3:
                    if area > best_area:
                        best_area = area
                        best_x = x
                        best_y = y
            
            if best_area > 0:
                return {"success": True, "x": best_x, "y": best_y, "method": "edge_detection"}
            
            # Method 2: Template matching if slider image provided
            if slider_image:
                slider_array = np.frombuffer(slider_image, np.uint8)
                slider_img = cv2.imdecode(slider_array, cv2.IMREAD_COLOR)
                
                result = cv2.matchTemplate(bg_img, slider_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                
                if max_val > 0.5:
                    return {"success": True, "x": max_loc[0], "y": max_loc[1], "method": "template_match"}
            
            return {"success": False, "x": 0, "y": 0, "method": "no_gap_found"}
            
        except Exception as e:
            log.error(f"Gap detection failed: {e}")
            return {"success": False, "x": 0, "y": 0, "method": f"error: {e}"}
    
    def generate_human_trajectory(
        self,
        distance: int,
        duration: float = 0.5,
        points: int = 20
    ) -> List[Tuple[int, float]]:
        """
        Generate human-like mouse movement trajectory.
        
        Args:
            distance: Total distance to move (pixels)
            duration: Total duration (seconds)
            points: Number of trajectory points
        
        Returns:
            List of (x_offset, delay) tuples
        """
        trajectory = []
        
        # Use ease-out cubic for natural deceleration
        for i in range(points):
            t = i / points
            # Ease-out cubic: 1 - (1-t)^3
            progress = 1 - math.pow(1 - t, 3)
            x = int(distance * progress)
            
            # Add slight randomness
            x += random.randint(-2, 2)
            x = max(0, min(distance, x))
            
            # Variable delay between movements
            delay = (duration / points) * (0.8 + random.random() * 0.4)
            
            trajectory.append((x, delay))
        
        # Ensure final position is exact
        trajectory.append((distance, 0.05))
        
        return trajectory
    
    def solve_slider(
        self,
        driver,
        slider_element,
        background_element=None,
        gap_x: int = None,
        timeout: float = 2.0
    ) -> dict:
        """
        Solve slider CAPTCHA by dragging slider to gap.
        
        Args:
            driver: WebDriver instance
            slider_element: Draggable slider element
            background_element: Background image element (for gap detection)
            gap_x: Known gap X position (if already detected)
            timeout: Max drag duration
        
        Returns:
            dict: {"success": bool, "distance": int, "method": str}
        """
        from selenium.webdriver.common.action_chains import ActionChains
        
        try:
            # Detect gap position if not provided
            if gap_x is None and background_element:
                bg_image = background_element.screenshot_as_png
                gap_result = self.find_slider_gap(bg_image)
                
                if gap_result["success"]:
                    gap_x = gap_result["x"]
                else:
                    return {"success": False, "distance": 0, "method": "gap_detection_failed"}
            
            if gap_x is None:
                return {"success": False, "distance": 0, "method": "no_gap_position"}
            
            # Calculate distance to move (gap_x minus slider starting position)
            slider_x = slider_element.location["x"]
            distance = gap_x - slider_x
            
            if distance <= 0:
                # Gap might be relative to background, try using gap_x directly
                distance = gap_x
            
            # Generate human-like trajectory
            trajectory = self.generate_human_trajectory(distance, timeout * 0.8)
            
            # Perform drag
            actions = ActionChains(driver)
            actions.click_and_hold(slider_element)
            
            last_x = 0
            for x, delay in trajectory:
                move_x = x - last_x
                if move_x != 0:
                    actions.move_by_offset(move_x, random.randint(-1, 1))
                last_x = x
            
            actions.release()
            actions.perform()
            
            # Brief pause to let page process
            time.sleep(0.3)
            
            return {"success": True, "distance": distance, "method": "drag_completed"}
            
        except Exception as e:
            log.error(f"Slider solve failed: {e}")
            return {"success": False, "distance": 0, "method": f"error: {e}"}
    
    def _call_api_ocr(self, image_data: bytes) -> dict:
        """Call third-party OCR API as fallback."""
        import requests
        
        if self.api_provider == "2captcha":
            return self._call_2captcha(image_data)
        elif self.api_provider == "anticaptcha":
            return self._call_anticaptcha(image_data)
        else:
            return {"success": False, "text": "", "method": "unknown_provider"}
    
    def _call_2captcha(self, image_data: bytes) -> dict:
        """Call 2captcha.com API."""
        import requests
        
        try:
            # Submit image
            resp = requests.post(
                "http://2captcha.com/in.php",
                data={
                    "key": self.api_key,
                    "method": "base64",
                    "body": base64.b64encode(image_data).decode()
                },
                timeout=30
            )
            
            if "OK|" not in resp.text:
                return {"success": False, "text": "", "method": "2captcha_submit_failed"}
            
            captcha_id = resp.text.split("|")[1]
            
            # Poll for result
            for _ in range(20):
                time.sleep(5)
                result = requests.get(
                    f"http://2captcha.com/res.php?key={self.api_key}&action=get&id={captcha_id}",
                    timeout=10
                )
                if "OK|" in result.text:
                    text = result.text.split("|")[1]
                    return {"success": True, "text": text, "method": "2captcha"}
                elif "CAPCHA_NOT_READY" not in result.text:
                    break
            
            return {"success": False, "text": "", "method": "2captcha_timeout"}
            
        except Exception as e:
            log.error(f"2captcha API error: {e}")
            return {"success": False, "text": "", "method": f"2captcha_error: {e}"}
    
    def _call_anticaptcha(self, image_data: bytes) -> dict:
        """Call anti-captcha.com API."""
        import requests
        
        try:
            # Create task
            resp = requests.post(
                "https://api.anti-captcha.com/createTask",
                json={
                    "clientKey": self.api_key,
                    "task": {
                        "type": "ImageToTextTask",
                        "body": base64.b64encode(image_data).decode()
                    }
                },
                timeout=30
            )
            
            data = resp.json()
            if data.get("errorId", 0) != 0:
                return {"success": False, "text": "", "method": f"anticaptcha_error: {data.get('errorDescription')}"}
            
            task_id = data["taskId"]
            
            # Poll for result
            for _ in range(20):
                time.sleep(5)
                result = requests.post(
                    "https://api.anti-captcha.com/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                    timeout=10
                ).json()
                
                if result.get("status") == "ready":
                    text = result.get("solution", {}).get("text", "")
                    return {"success": True, "text": text, "method": "anticaptcha"}
                elif result.get("status") != "processing":
                    break
            
            return {"success": False, "text": "", "method": "anticaptcha_timeout"}
            
        except Exception as e:
            log.error(f"anticaptcha API error: {e}")
            return {"success": False, "text": "", "method": f"anticaptcha_error: {e}"}


# Module-level convenience functions
_default_solver = None


def get_solver(api_key: str = None, api_provider: str = "2captcha") -> CaptchaSolver:
    """Get or create default CAPTCHA solver."""
    global _default_solver
    if _default_solver is None or api_key:
        _default_solver = CaptchaSolver(api_key, api_provider)
    return _default_solver


def recognize(image_data: bytes) -> dict:
    """Recognize text from image CAPTCHA."""
    return get_solver().recognize_image(image_data)


def solve_slider(driver, slider_element, background_element=None, gap_x: int = None) -> dict:
    """Solve slider CAPTCHA."""
    return get_solver().solve_slider(driver, slider_element, background_element, gap_x)


def find_gap(background_image: bytes, slider_image: bytes = None) -> dict:
    """Find gap position in slider CAPTCHA."""
    return get_solver().find_slider_gap(background_image, slider_image)


def check_dependencies() -> dict:
    """Check which CAPTCHA dependencies are available."""
    return {
        "ddddocr": DDDDOCR_AVAILABLE,
        "cv2": CV2_AVAILABLE,
        "message": (
            "All dependencies available" if DDDDOCR_AVAILABLE and CV2_AVAILABLE
            else "Missing: " + ", ".join(
                [x for x, avail in [("ddddocr", DDDDOCR_AVAILABLE), ("cv2/opencv", CV2_AVAILABLE)] if not avail]
            )
        )
    }

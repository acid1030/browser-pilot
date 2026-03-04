"""
Browser Pilot - Chrome Profile Manager
Instead of reading Chrome's locked Cookie SQLite file directly,
this module copies the entire Chrome profile directory.
This works even when Chrome is running (like Playwright's persistent context).
"""
import os
import shutil
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict

log = logging.getLogger("browser-pilot.chrome")

# Chrome profile paths on different platforms
CHROME_PATHS = {
    "darwin": Path.home() / "Library" / "Application Support" / "Google" / "Chrome",
    "linux": Path.home() / ".config" / "google-chrome",
    "win32": Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
}

# Where we store copied profiles
COPIED_PROFILES_DIR = Path.home() / ".qoder" / "browser-pilot" / "chrome-imports"


def get_chrome_base_path() -> Optional[Path]:
    """Get Chrome user data directory for current platform."""
    import platform
    system = platform.system().lower()
    
    if system == "darwin":
        key = "darwin"
    elif system == "windows":
        key = "win32"
    else:
        key = "linux"
    
    chrome_path = CHROME_PATHS.get(key)
    if chrome_path and chrome_path.exists():
        return chrome_path
    return None


def list_chrome_profiles() -> List[str]:
    """
    List available Chrome profiles.
    
    Returns:
        List of profile names (e.g., ["Default", "Profile 1", "Profile 2"])
    """
    chrome_path = get_chrome_base_path()
    if not chrome_path:
        return []
    
    profiles = []
    
    # Check Default profile
    if (chrome_path / "Default").exists():
        profiles.append("Default")
    
    # Check numbered profiles
    for item in chrome_path.iterdir():
        if item.is_dir() and item.name.startswith("Profile "):
            profiles.append(item.name)
    
    return profiles


def get_profile_path(profile: str = "Default") -> Optional[Path]:
    """Get full path to a Chrome profile directory."""
    chrome_path = get_chrome_base_path()
    if not chrome_path:
        return None
    
    profile_path = chrome_path / profile
    if profile_path.exists():
        return profile_path
    return None


def copy_chrome_profile(
    chrome_profile: str = "Default",
    target_name: Optional[str] = None,
    force: bool = False
) -> Dict:
    """
    Copy Chrome profile directory to browser-pilot's isolated storage.
    This works even when Chrome is running.
    
    Args:
        chrome_profile: Chrome profile name (Default, Profile 1, etc.)
        target_name: Name for the copied profile (defaults to chrome_profile + timestamp)
        force: If True, overwrite existing copy
    
    Returns:
        dict: {
            "success": bool,
            "path": str or None,  # Path to copied profile
            "message": str
        }
    """
    source_path = get_profile_path(chrome_profile)
    if not source_path:
        return {
            "success": False,
            "path": None,
            "message": f"Chrome profile '{chrome_profile}' not found"
        }
    
    # Create target directory
    COPIED_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    if target_name is None:
        target_name = f"{chrome_profile}_{int(time.time())}"
    
    target_path = COPIED_PROFILES_DIR / target_name
    
    # Check if already exists
    if target_path.exists():
        if force:
            log.info(f"Removing existing profile copy: {target_path}")
            shutil.rmtree(target_path, ignore_errors=True)
        else:
            return {
                "success": True,
                "path": str(target_path),
                "message": f"Profile copy already exists at {target_path}"
            }
    
    try:
        log.info(f"Copying Chrome profile from {source_path} to {target_path}...")
        
        # Copy profile directory
        # Use copy2 to preserve metadata, ignore_dangling_symlinks for safety
        # We only copy essential files to save space and time
        target_path.mkdir(parents=True, exist_ok=True)
        
        # Essential files/dirs for cookie and session data
        essential_items = [
            "Cookies",           # Cookie database
            "Cookies-journal",   # Cookie journal
            "Login Data",        # Saved passwords
            "Login Data-journal",
            "Web Data",          # Autofill data
            "Web Data-journal",
            "Local Storage",     # LocalStorage
            "Session Storage",   # SessionStorage
            "IndexedDB",         # IndexedDB
            "Preferences",       # Profile preferences
            "Secure Preferences",
            "Network",           # Network state
            "History",           # Browser history (optional, but useful)
            "History-journal",
        ]
        
        copied_count = 0
        for item in essential_items:
            source_item = source_path / item
            target_item = target_path / item
            
            if source_item.exists():
                try:
                    if source_item.is_dir():
                        shutil.copytree(source_item, target_item, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source_item, target_item)
                    copied_count += 1
                except (PermissionError, OSError) as e:
                    # Some files might be locked, continue with others
                    log.debug(f"Could not copy {item}: {e}")
        
        if copied_count == 0:
            return {
                "success": False,
                "path": None,
                "message": "No essential files could be copied (Chrome might be restricting access)"
            }
        
        log.info(f"Copied {copied_count} items to {target_path}")
        return {
            "success": True,
            "path": str(target_path),
            "message": f"Profile copied successfully ({copied_count} items)"
        }
        
    except PermissionError as e:
        return {
            "success": False,
            "path": None,
            "message": f"Permission denied: {e}"
        }
    except Exception as e:
        return {
            "success": False,
            "path": None,
            "message": f"Copy failed: {e}"
        }


def copy_chrome_profile_full(
    chrome_profile: str = "Default",
    target_name: Optional[str] = None,
    force: bool = False
) -> Dict:
    """
    Copy entire Chrome profile directory (full copy for use with --user-data-dir).
    This includes all extensions, settings, etc.
    
    WARNING: This can be slow and use significant disk space (1GB+).
    
    Args:
        chrome_profile: Chrome profile name
        target_name: Name for copied profile
        force: Overwrite existing
    
    Returns:
        dict with success, path, message
    """
    chrome_base = get_chrome_base_path()
    if not chrome_base:
        return {
            "success": False,
            "path": None,
            "message": "Chrome installation not found"
        }
    
    source_profile = chrome_base / chrome_profile
    if not source_profile.exists():
        return {
            "success": False,
            "path": None,
            "message": f"Chrome profile '{chrome_profile}' not found"
        }
    
    COPIED_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    if target_name is None:
        target_name = f"full_{chrome_profile}_{int(time.time())}"
    
    # Create a user-data-dir structure (Chrome expects this layout)
    target_base = COPIED_PROFILES_DIR / target_name
    target_profile = target_base / "Default"  # Always use Default for copied profiles
    
    if target_base.exists():
        if force:
            shutil.rmtree(target_base, ignore_errors=True)
        else:
            return {
                "success": True,
                "path": str(target_base),
                "message": f"Profile already exists at {target_base}"
            }
    
    try:
        log.info(f"Full copy of Chrome profile from {source_profile}...")
        
        # Copy with robocopy-like approach: ignore errors, continue copying
        def copy_with_ignore(src, dst):
            """Copy tree, ignoring errors."""
            if not os.path.exists(dst):
                os.makedirs(dst)
            
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                
                # Skip some problematic dirs
                skip_dirs = ["Cache", "Code Cache", "GPUCache", "Service Worker", 
                            "ShaderCache", "GrShaderCache", "blob_storage",
                            "Crashpad", "BrowserMetrics"]
                if item in skip_dirs:
                    continue
                
                try:
                    if os.path.isdir(s):
                        copy_with_ignore(s, d)
                    else:
                        shutil.copy2(s, d)
                except (PermissionError, OSError, shutil.Error) as e:
                    log.debug(f"Skipped {item}: {e}")
                    continue
        
        target_base.mkdir(parents=True, exist_ok=True)
        copy_with_ignore(str(source_profile), str(target_profile))
        
        # Copy essential parent-level files
        parent_files = ["Local State"]
        for f in parent_files:
            src = chrome_base / f
            dst = target_base / f
            if src.exists():
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass
        
        return {
            "success": True,
            "path": str(target_base),
            "message": f"Full profile copied to {target_base}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "path": None,
            "message": f"Full copy failed: {e}"
        }


def get_copied_profiles() -> List[Dict]:
    """
    List all copied Chrome profiles.
    
    Returns:
        List of dicts: [{"name": str, "path": str, "created": float}]
    """
    if not COPIED_PROFILES_DIR.exists():
        return []
    
    profiles = []
    for item in COPIED_PROFILES_DIR.iterdir():
        if item.is_dir():
            profiles.append({
                "name": item.name,
                "path": str(item),
                "created": item.stat().st_mtime
            })
    
    return sorted(profiles, key=lambda x: x["created"], reverse=True)


def get_latest_copied_profile(chrome_profile: str = "Default") -> Optional[str]:
    """
    Get the most recent copy of a Chrome profile.
    
    Args:
        chrome_profile: Original Chrome profile name
    
    Returns:
        Path to the copied profile, or None
    """
    profiles = get_copied_profiles()
    
    # Look for full copies first (they work with --user-data-dir)
    for p in profiles:
        if p["name"].startswith(f"full_{chrome_profile}_"):
            return p["path"]
    
    # Then regular copies
    for p in profiles:
        if p["name"].startswith(f"{chrome_profile}_"):
            return p["path"]
    
    return None


def cleanup_old_profiles(keep_count: int = 3) -> int:
    """
    Remove old copied profiles, keeping the most recent ones.
    
    Args:
        keep_count: Number of recent profiles to keep
    
    Returns:
        Number of profiles removed
    """
    profiles = get_copied_profiles()
    
    if len(profiles) <= keep_count:
        return 0
    
    removed = 0
    for p in profiles[keep_count:]:
        try:
            shutil.rmtree(p["path"])
            removed += 1
            log.info(f"Removed old profile copy: {p['name']}")
        except Exception as e:
            log.warning(f"Failed to remove {p['name']}: {e}")
    
    return removed


def has_chrome_cookies(site: str, profile: str = "Default") -> bool:
    """
    Check if Chrome profile likely has cookies for a site.
    This checks if the profile has a Cookies file.
    
    Args:
        site: Domain to check
        profile: Chrome profile name
    
    Returns:
        bool indicating if cookies likely exist
    """
    profile_path = get_profile_path(profile)
    if not profile_path:
        return False
    
    cookies_file = profile_path / "Cookies"
    return cookies_file.exists() and cookies_file.stat().st_size > 0


# Legacy compatibility - these are kept for backwards compatibility
# but the new approach is to copy the profile directory

def get_chrome_cookies(domain, profile="Default"):
    """
    Legacy function - attempts to read cookies using browser_cookie3.
    May fail if Chrome is running. Prefer using copy_chrome_profile() instead.
    """
    try:
        import browser_cookie3
    except ImportError:
        log.warning("browser_cookie3 not installed. Run: pip install browser_cookie3")
        return []
    
    cookies = []
    
    try:
        cj = browser_cookie3.chrome(domain_name=domain)
        
        for cookie in cj:
            selenium_cookie = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
                "httpOnly": cookie.has_nonstandard_attr("HttpOnly"),
            }
            
            if cookie.expires:
                selenium_cookie["expiry"] = cookie.expires
            
            cookies.append(selenium_cookie)
        
        log.info(f"Found {len(cookies)} cookies for domain '{domain}' in Chrome")
        return cookies
        
    except Exception as e:
        log.warning(f"Failed to read Chrome cookies (Chrome running?): {e}")
        return []


def get_chrome_cookies_for_site(site, profile="Default"):
    """
    Legacy function - get cookies for a site using browser_cookie3.
    May fail if Chrome is running. Prefer using copy_chrome_profile() instead.
    """
    domain = site.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    
    patterns = [f".{domain}", domain]
    
    all_cookies = []
    seen = set()
    
    for pattern in patterns:
        cookies = get_chrome_cookies(pattern, profile)
        for cookie in cookies:
            key = (cookie["name"], cookie["domain"], cookie["path"])
            if key not in seen:
                seen.add(key)
                all_cookies.append(cookie)
    
    return all_cookies

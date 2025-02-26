"""
SSL certificate fix for macOS.

This module provides a fix for SSL certificate verification issues on macOS.
"""
import os
import ssl
import sys
import platform
import subprocess
from typing import Optional


def fix_macos_ssl_certificates() -> bool:
    """
    Fix SSL certificate verification issues on macOS.
    
    On macOS, Python doesn't use the system's certificate store by default,
    which can cause SSL verification errors. This function attempts to
    install certificates for the current Python environment.
    
    Returns:
        bool: True if certificates were successfully installed or already working,
              False if the fix couldn't be applied
    """
    # Only apply fix on macOS
    if platform.system() != 'Darwin':
        return True
        
    # Check if certificates are already working
    try:
        import urllib.request
        urllib.request.urlopen('https://www.google.com')
        return True  # SSL already working
    except ssl.SSLError:
        pass  # Need to fix certificates
    except Exception:
        return False  # Some other error, can't fix
        
    # Try to locate the certificate installation script
    cert_script = get_certifi_script_path()
    if not cert_script:
        return False
        
    try:
        # Run the certificate installation script
        result = subprocess.run(
            [sys.executable, cert_script],
            capture_output=True,
            text=True,
            check=True
        )
        return "SSL certificates installed" in result.stdout
    except subprocess.CalledProcessError:
        return False
    except Exception:
        return False


def get_certifi_script_path() -> Optional[str]:
    """
    Find the path to the macOS certificate installation script.
    
    Returns:
        Optional[str]: Path to the certificate script if found, None otherwise
    """
    # Check common locations
    potential_paths = [
        '/Applications/Python 3.x/Install Certificates.command',
        '/Applications/Python/Install Certificates.command',
        '/Applications/Python 3.10/Install Certificates.command',
        '/Applications/Python 3.9/Install Certificates.command',
        '/Applications/Python 3.11/Install Certificates.command',
        f'{os.path.expanduser("~")}/Library/Python/3.x/lib/python/site-packages/pip/_vendor/certifi/cacert.pem',
    ]
    
    # Try to find by searching Applications folder
    python_dirs = [d for d in os.listdir('/Applications') if d.startswith('Python')]
    for d in python_dirs:
        cert_path = f'/Applications/{d}/Install Certificates.command'
        if os.path.exists(cert_path):
            return cert_path
            
    # Check if certifi is installed
    try:
        import certifi
        return certifi.where()
    except ImportError:
        pass
        
    # Check potential paths
    for path in potential_paths:
        if os.path.exists(path):
            return path
            
    return None


def disable_ssl_verification() -> None:
    """
    Disable SSL certificate verification (USE ONLY FOR DEVELOPMENT).
    
    This is a TEMPORARY workaround and should NOT be used in production as it 
    makes your application vulnerable to man-in-the-middle attacks.
    """
    # Create an unverified SSL context
    ssl._create_default_https_context = ssl._create_unverified_context 
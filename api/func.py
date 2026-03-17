import requests
import bs4
from typing import Union

def authorize(login: str, password: str) -> Union[bool, tuple[str, str]]:
    """
    Checks if user is student or not
    If student return fullname and faculty
    Otherwise return False
    """
    try:
        print(f"[AUTH] Attempting authorize with login={login}")
        
        session = requests.Session()
        response = session.get("https://bntu.by/user/login", verify=False)
        print(f"[AUTH] Login page status: {response.status_code}")
        content = response.text
        cookies = response.cookies
        
        soup = bs4.BeautifulSoup(content, "html.parser")
        token_element = soup.form.find("input", attrs={"name": "_token"})
        if not token_element:
            print("[AUTH] ERROR: Could not find CSRF token")
            return False
            
        token = token_element["value"]
        print(f"[AUTH] Token extracted: {token[:20]}...")
        
        headers = {
            "cookie": f"XSRF-TOKEN={cookies.get('XSRF-TOKEN', '')}; laravel_session={cookies.get('laravel_session', '')}"
        }
        
        data = {"_token": token, "username": login, "password": password}
        
        response = session.post(
            "https://bntu.by/user/auth", headers=headers, data=data, verify=False
        )
        content = response.text
        print(f"[AUTH] Auth response status: {response.status_code}")
        print(f"[AUTH] Auth response URL: {response.url}")
        
        if "pay" in str(response.url):
            soup = bs4.BeautifulSoup(content, "html.parser")
            fullname_element = soup.find("h1", class_="newsName")
            if not fullname_element:
                print("[AUTH] ERROR: Could not find fullname element")
                return False
                
            fullname = fullname_element.next_sibling.next_sibling.text.split(",")[1][1:-22]
            info_div = soup.find("div", class_="dashboardInfo")
            if not info_div:
                print("[AUTH] ERROR: Could not find dashboardInfo div")
                return False
                
            for line in info_div.contents:
                if "курс" in line:
                    _, _, faculty, *_ = line.split(",")
                    break
            faculty = faculty.replace(" ", "")
            print(f"[AUTH] Authorization success: {fullname}, {faculty}")
            return fullname, faculty
        else:
            print(f"[AUTH] Authorization failed: not redirected to pay page")
            print(f"[AUTH] Response content preview: {content[:500]}...")
            return False
            
    except Exception as e:
        print(f"[AUTH] Authorization error: {e}")
        return False
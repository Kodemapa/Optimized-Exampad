import re
from app import create_app


def extract_csrf(html):
    m = re.search(r"name=\"csrf-token\" content=\"([^\"]+)\"", html)
    if m:
        return m.group(1)
    # fallback: look for hidden input
    m2 = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if m2:
        return m2.group(1)
    return None


def run_test():
    app = create_app()
    with app.test_client() as client:
        # GET login page to retrieve CSRF token
        r = client.get('/auth/login')
        html = r.get_data(as_text=True)
        token = extract_csrf(html)
        print('Login page csrf token:', token)

        # POST login
        resp = client.post('/auth/login', data={'username': 'sadmin', 'password': 'sadmin@123', 'csrf_token': token}, follow_redirects=True)
        print('Login status code:', resp.status_code)

        # GET theme page
        r2 = client.get('/admin/theme')
        html2 = r2.get_data(as_text=True)
        token2 = extract_csrf(html2)
        print('Theme page csrf token:', token2)

        # POST theme update
        resp2 = client.post('/admin/theme', data={'theme': 'blue', 'csrf_token': token2}, follow_redirects=True)
        print('Theme update status:', resp2.status_code)
        if resp2.status_code == 200:
            print('Theme update page loaded after POST')
        else:
            print('Theme update response length:', len(resp2.get_data(as_text=True)))


if __name__ == '__main__':
    run_test()

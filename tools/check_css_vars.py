from app import create_app
from app.models import SiteSetting
app=create_app()
with app.test_client() as c:
    # ensure theme is set to 'blue' for test
    SiteSetting.set('ui_theme','blue')
    r=c.get('/auth/login')
    html=r.get_data(as_text=True)
    start=html.find(':root')
    snippet=html[start:start+300]
    print('snippet with :root block:\n', snippet)
    # check for btn-primary rule
    found = 'btn-primary' in html
    print('btn-primary in page:', found)
    # dump site_primary
    print('site_primary from context:', SiteSetting.get('ui_theme'))

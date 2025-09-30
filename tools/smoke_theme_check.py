from app import create_app
app=create_app()
with app.test_client() as c:
    r=c.get('/auth/login')
    s = r.get_data(as_text=True)
    print('login page snippet length:', len(s))
    r2 = c.get('/admin/theme')
    print('admin theme page length:', len(r2.get_data(as_text=True)))

"""
KODEMAPA-EXAMPAD Application Factory
"""

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import config

# Import db from models to avoid circular imports
from app.models import db

# Initialize other extensions
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app(config_name='default'):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Add custom Jinja2 filters
    @app.template_filter('ord')
    def ord_filter(char):
        """Convert character to ASCII value"""
        return ord(char[0]) if char and len(char) > 0 else 0
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # User loader function for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))
    
    # Import and register blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.exam import bp as exam_bp
    app.register_blueprint(exam_bp, url_prefix='/exam')
    
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    # Exempt API blueprint from CSRF protection
    csrf.exempt(api_bp)

    # Inject site-wide settings into templates
    @app.context_processor
    def inject_site_settings():
        try:
            from app.models import SiteSetting
            current_theme = SiteSetting.get('ui_theme', default='original')
        except Exception:
            current_theme = 'original'

        theme_map = {
            'original': '#2596be',
            'default': '#667eea',
            'blue': '#0d6efd',
            'green': '#198754',
            'dark': '#343a40',
            'sunset': '#ff7e5f'
        }
        primary = theme_map.get(current_theme, theme_map['original'])
        # Define a simple secondary mapping (a darker or complementary shade)
        secondary_map = {
            'original': '#207381',
            'default': '#5a67d8',
            'blue': '#0b5ed7',
            'green': '#157347',
            'dark': '#212529',
            'sunset': '#e85a3f'
        }
        secondary = secondary_map.get(current_theme, secondary_map['original'])
        # Read site title (default fallback)
        try:
            site_title = SiteSetting.get('site_title', default='AKSHARASHREE')
        except Exception:
            site_title = 'AKSHARASHREE'
        return dict(site_theme=current_theme, site_primary=primary, site_secondary=secondary, site_title=site_title)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app

"""
KODEMAPA-EXAMPAD Application Runner
Main entry point for the full exam platform
"""

import os
from app import create_app

# Create Flask application
app = create_app(os.environ.get('FLASK_CONFIG', 'development'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6001, debug=True)

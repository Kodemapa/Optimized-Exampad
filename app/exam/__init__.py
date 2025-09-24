"""
Exam Blueprint - Exam taking and management
"""

from flask import Blueprint

bp = Blueprint('exam', __name__)

from app.exam import routes

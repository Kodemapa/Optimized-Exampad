from flask_login import current_user
from app.models import StudentClass, db, User

def get_student_class(user_id):
    user = User.query.get(user_id)
    if user and user.student_class:
        return user.student_class.class_level
    return None

def update_student_class(user_id, new_class_name):
    user = User.query.get(user_id)
    if not user:
        return False
    student_class = StudentClass.query.filter_by(name=new_class_name).first()
    if not student_class:
        return False
    user.student_class_id = student_class.id
    db.session.commit()
    return True

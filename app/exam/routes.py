## Place this route after all imports and after bp is defined

# ...existing code...


# ...existing code...

from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.exam import bp
from app.models import db, Subject, Topic, Question, Exam, ExamSession
from app import csrf
import random
from datetime import datetime, timedelta
import time
from sqlalchemy.orm import sessionmaker
import os
import json

@bp.route('/results/json', methods=['GET'])
@login_required
def results_json():
    """Return analytics JSON for the current user."""
    from sqlalchemy import func
    # Get all user sessions with eager loading
    try:
        db.session.remove()
        fresh_count = ExamSession.query.filter_by(user_id=current_user.id).count()
        current_app.logger.info(f"Fresh session count for user {current_user.id}: {fresh_count}")
        time.sleep(0.5)
        Session = sessionmaker(bind=db.engine)
        fresh_session = Session()
        from sqlalchemy.orm import joinedload
        sessions = fresh_session.query(ExamSession).options(joinedload(ExamSession.exam))\
                                .filter_by(user_id=current_user.id)\
                                .order_by(ExamSession.start_time.desc()).all()
        sessions_with_exam_titles = []
        for session in sessions:
            class SessionWrapper:
                def __init__(self, s, exam_title):
                    self.id = s.id
                    self.exam_title = exam_title
                    self.start_time = s.start_time
                    self.percentage = s.percentage
                    self.score = s.score
                    self.max_score = s.max_score
                    self.duration_seconds = getattr(s, 'duration_seconds', None)
            exam_title = session.exam.title if session.exam else 'Practice Test'
            session_wrapper = SessionWrapper(session, exam_title)
            sessions_with_exam_titles.append(session_wrapper)
        sessions = sessions_with_exam_titles
        total_sessions = len(sessions)
        valid_scores = [session.percentage for session in sessions if session.percentage is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        best_session = max(sessions, key=lambda s: s.percentage if s.percentage is not None else -1, default=None)
        worst_session = min(sessions, key=lambda s: s.percentage if s.percentage is not None else 101, default=None)
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'correct': 0, 'total': 0}, 'moderate': {'correct': 0, 'total': 0}, 'difficult': {'correct': 0, 'total': 0}}
        for session in sessions:
            # You may want to add more detailed aggregation here
            pass
        for subject in subject_stats.values():
            subject['percentage'] = (subject['correct'] / subject['total'] * 100) if subject['total'] > 0 else 0
        for topic in topic_stats.values():
            topic['percentage'] = (topic['correct'] / topic['total'] * 100) if topic['total'] > 0 else 0
        for difficulty in difficulty_stats.values():
            difficulty['percentage'] = (difficulty['correct'] / difficulty['total'] * 100) if difficulty['total'] > 0 else 0
        recent_sessions = sessions[:5] if sessions else []
        trend_sessions = sessions[:10] if sessions else []
        performance_trend = [{'date': session.start_time.strftime('%m/%d'), 'percentage': session.percentage} for session in reversed(trend_sessions)]
        def session_to_dict(session):
            return {
                'id': getattr(session, 'id', None),
                'exam_title': getattr(session, 'exam_title', None),
                'start_time': session.start_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(session, 'start_time') and session.start_time else None,
                'percentage': getattr(session, 'percentage', None),
                'score': getattr(session, 'score', None),
                'max_score': getattr(session, 'max_score', None),
                'duration_seconds': getattr(session, 'duration_seconds', None),
            }
        return jsonify({
            'sessions': [session_to_dict(s) for s in sessions],
            'recent_sessions': [session_to_dict(s) for s in recent_sessions],
            'total_sessions': total_sessions,
            'avg_score': round(avg_score, 1),
            'best_session': session_to_dict(best_session) if best_session else None,
            'worst_session': session_to_dict(worst_session) if worst_session else None,
            'subject_stats': subject_stats,
            'topic_stats': topic_stats,
            'difficulty_stats': difficulty_stats,
            'performance_trend': performance_trend
        })
    except Exception as e:
        current_app.logger.error(f"Error in results_json: {e}")
        return jsonify({'error': str(e)}), 500

# ...existing code...

from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.exam import bp
from app.models import db, Subject, Topic, Question, Exam, ExamSession
from app import csrf
import random
from datetime import datetime, timedelta, timezone
import time
from sqlalchemy.orm import sessionmaker
import os
import json

from flask import current_app
from sqlalchemy import text

# Ensure DB shape is compatible with current models (lightweight safety)
def ensure_customtest_details_column():
    try:
        # Works on SQLite; harmless if column already exists
        result = db.session.execute(text("PRAGMA table_info(customTests)"))
        column_names = []
        for row in result:
            try:
                name = row[1]
            except Exception:
                name = row.get('name') if isinstance(row, dict) else None
            if name:
                column_names.append(name)
        if 'details_json' not in column_names:
            db.session.execute(text("ALTER TABLE customTests ADD COLUMN details_json TEXT"))
            db.session.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not ensure details_json column on customTests: {e}")
        db.session.rollback()


def refresh_and_persist_custom_test_status(custom_test):
    """Refresh CustomTest.status based on start/end times and persist when changed."""
    try:
        if not custom_test:
            return
        now = datetime.utcnow()
        new_status = 'active'
        if custom_test.started_at and now < custom_test.started_at:
            new_status = 'scheduled'
        elif custom_test.closed_at and now >= custom_test.closed_at:
            new_status = 'inactive'
        if custom_test.status != new_status:
            custom_test.status = new_status
            db.session.commit()
    except Exception as e:
        current_app.logger.warning(f"Could not refresh CustomTest status: {e}")


# Lightweight periodic sweep to persist status changes when windows pass
_last_status_sweep_ts = 0

@bp.before_app_request
def sweep_custom_tests_status_periodically():
    global _last_status_sweep_ts
    try:
        now_ts = time.time()
        # Run at most once every 60 seconds per worker
        if _last_status_sweep_ts and (now_ts - _last_status_sweep_ts) < 60:
            return
        _last_status_sweep_ts = now_ts

        from app.models import CustomTest
        now = datetime.utcnow()

        # Set tests to inactive if closed_at has passed and status is not yet inactive
        to_inactivate = CustomTest.query.filter(
            CustomTest.closed_at.isnot(None),
            CustomTest.closed_at <= now,
            CustomTest.status != 'inactive'
        ).all()
        changed = False
        for ct in to_inactivate:
            ct.status = 'inactive'
            changed = True

        # Optionally bump scheduled->active if window opened (without closed_at yet or not passed)
        to_activate = CustomTest.query.filter(
            CustomTest.started_at.isnot(None),
            CustomTest.started_at <= now,
            (CustomTest.closed_at.is_(None)) | (CustomTest.closed_at > now),
            CustomTest.status != 'active'
        ).all()
        for ct in to_activate:
            ct.status = 'active'
            changed = True

        if changed:
            db.session.commit()
    except Exception as e:
        # Do not block requests for sweep errors
        current_app.logger.warning(f"Periodic status sweep failed: {e}")
        db.session.rollback()

# API endpoint to get topics for a subject
@bp.route('/get_topics/<int:subject_id>')
@login_required
def get_topics_for_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    topics = [{'id': t.id, 'name': t.name} for t in subject.topics]
    return jsonify({'topics': topics})

# API endpoint to get questions for a topic (with options and explanation)
@bp.route('/get_questions_by_topic/<int:topic_id>')
@login_required
def get_questions_by_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    questions = []
    for question in topic.questions:
        # Only include questions with both options and explanation
        if question.options and question.explanation:
            questions.append({
                'id': question.id,
                'text': question.question_text,
                'options': question.get_options()  # include options for UI rendering
            })
    return jsonify({'questions': questions})


from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.exam import bp
from app.models import db, Subject, Topic, Question, Exam, ExamSession
from app import csrf
import random
from datetime import datetime, timedelta
import time
from sqlalchemy.orm import sessionmaker
import os
import json

from flask import current_app

# API endpoint to get questions for a subject
@bp.route('/get_questions/<int:subject_id>')
@login_required
def get_questions_for_subject(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    topics_data = []
    for topic in subject.topics:
        topic_questions = []
        for question in topic.questions:
            topic_questions.append({
                'id': question.id,
                'text': question.question_text  # Full text for display
            })
        topics_data.append({
            'topic_id': topic.id,
            'topic_name': topic.name,
            'questions': topic_questions
        })
    return jsonify({'topics': topics_data})

from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.exam import bp
from app.models import db, Subject, Topic, Question, Exam, ExamSession
from app import csrf
import random
from datetime import datetime, timedelta
import time
from sqlalchemy.orm import sessionmaker
import os
import json

from flask import current_app



# ...existing code...

# Place this route after all imports and after bp is defined

"""
Exam Blueprint Routes - Exam taking and management
"""

from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.exam import bp
from app.models import db, Subject, Topic, Question, Exam, ExamSession
from app import csrf
import random
from datetime import datetime, timedelta
import time
from sqlalchemy.orm import sessionmaker
import os
import json

from flask import current_app

@bp.route('/create_test', methods=['GET', 'POST'])
@login_required
def create_test():
    """Allow teachers to create a test for students"""
    if getattr(current_user, 'role', None) != 'teacher':
        flash('Access denied: Only teachers can create tests.', 'error')
        return redirect(url_for('main.dashboard'))

    if request.method == 'GET':
        class_xi_subjects = Subject.query.filter_by(class_level='XI').all()
        class_xii_subjects = Subject.query.filter_by(class_level='XII').all()
        return render_template('exam/create_test.html', class_xi_subjects=class_xi_subjects, class_xii_subjects=class_xii_subjects)

    # POST: Handle form submission
    class_level = request.form.get('class_level')
    subject_id = request.form.get('subject_id')
    # Prefer ordered selection from the Selected list; fallback to raw checkboxes
    ordered_ids = request.form.getlist('selected_question_ids')
    if not ordered_ids:
        ordered_ids = request.form.getlist('question_ids')
    duration_minutes = request.form.get('duration_minutes', type=int)
    start_datetime_str = request.form.get('start_datetime')
    end_datetime_str = request.form.get('end_datetime')
    positive_mark = request.form.get('positive_mark', type=int)
    negative_mark = request.form.get('negative_mark', type=int)

    if not class_level or not subject_id or not ordered_ids:
        flash('Please select class, subject, and questions.', 'error')
        return redirect(url_for('exam.create_test'))
    if not duration_minutes or duration_minutes <= 0:
        flash('Please provide a valid duration in minutes.', 'error')
        return redirect(url_for('exam.create_test'))
    # Validate marking scheme
    if positive_mark is None or positive_mark < 0:
        flash('Please provide a valid positive mark (>= 0).', 'error')
        return redirect(url_for('exam.create_test'))
    if negative_mark is None or negative_mark < 0:
        flash('Please provide a valid negative mark (>= 0).', 'error')
        return redirect(url_for('exam.create_test'))

    subject = Subject.query.get(subject_id)
    # Fetch and then order questions according to posted order
    questions_all = Question.query.filter(Question.id.in_(ordered_ids)).all()
    questions_by_id = {str(q.id): q for q in questions_all}
    ordered_questions = [questions_by_id[qid] for qid in ordered_ids if str(qid) in questions_by_id]
    exam_title = f"Custom Test by {current_user.username} - {subject.name} ({class_level})"

    exam = Exam(
        title=exam_title,
        subject_id=subject.id,
        created_by=current_user.id,
        duration_minutes=duration_minutes,
        created_at=datetime.utcnow()
    )
    db.session.add(exam)
    db.session.commit()

    try:
        # If Exam<->Question relationship exists, preserve the specified order
        for q in ordered_questions:
            exam.questions.append(q)
        db.session.commit()
    except Exception as rel_err:
        # Relationship may not exist; continue without failing creation
        current_app.logger.warning(f"Unable to attach questions to exam (relationship missing?): {rel_err}")

    # Create CustomTest lifecycle record
    link_url = None
    try:
        from app.models import CustomTest
        # Parse datetimes if provided (HTML datetime-local -> 'YYYY-MM-DDTHH:MM')
        started_at = None
        closed_at = None
        if start_datetime_str:
            try:
                # Parse as IST (Asia/Kolkata) and convert to UTC naive
                IST = timezone(timedelta(hours=5, minutes=30))
                started_local = datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M')
                started_at = started_local.replace(tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass
        if end_datetime_str:
            try:
                IST = timezone(timedelta(hours=5, minutes=30))
                closed_local = datetime.strptime(end_datetime_str, '%Y-%m-%dT%H:%M')
                closed_at = closed_local.replace(tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass
        status = 'active'
        now = datetime.utcnow()
        if started_at and now < started_at:
            status = 'scheduled'
        if closed_at and now >= closed_at:
            status = 'inactive'

        custom_test = CustomTest(
            exam_id=exam.id,
            created_by_user_id=current_user.id,
            created_by_username=current_user.username,
            started_at=started_at,
            closed_at=closed_at,
            status=status,
            number_of_students_taken=0,
            positive_marks=int(positive_mark),
            negative_marks=int(negative_mark)
        )
        db.session.add(custom_test)
        db.session.commit()
        # Store full test details JSON, including ordered question IDs
        try:
            details = {
                'class_level': class_level,
                'subject_id': int(subject_id) if subject_id else None,
                'subject_name': subject.name if subject else None,
                'duration_minutes': duration_minutes,
                'start_datetime': start_datetime_str,
                'end_datetime': end_datetime_str,
                'marking_scheme': {
                    'positive': int(positive_mark),
                    'negative': int(negative_mark)
                },
                'ordered_question_ids': [int(qid) for qid in ordered_ids if str(qid).isdigit()],
                'exam_id': exam.id,
                'title': exam_title
            }
            # Attempt to set details_json; if column missing, add it on-the-fly
            try:
                setattr(custom_test, 'details_json', json.dumps(details))
                db.session.commit()
            except Exception as col_err:
                current_app.logger.warning(f"details_json column missing on CustomTest, attempting to add: {col_err}")
                try:
                    db.session.execute("ALTER TABLE customTests ADD COLUMN details_json TEXT")
                    db.session.commit()
                    setattr(custom_test, 'details_json', json.dumps(details))
                    db.session.commit()
                except Exception as alter_err:
                    current_app.logger.error(f"Failed to add details_json column: {alter_err}")
                    db.session.rollback()
        except Exception as det_err:
            current_app.logger.error(f"Failed to store custom test details: {det_err}")
        link_url = url_for('exam.custom_link', exam_id=exam.id, _external=True)
    except Exception as e:
        current_app.logger.error(f"Failed to create CustomTest record: {e}")
        db.session.rollback()

    if link_url:
        try:
            submissions_url = url_for('exam.custom_test_submissions', exam_id=exam.id, _external=False)
            flash(f'Test created successfully! Share link: {link_url} | View submissions: {submissions_url}', 'success')
        except Exception:
            flash(f'Test created successfully! Share link: {link_url}', 'success')
    else:
        flash('Test created successfully!', 'success')
    return redirect(url_for('main.dashboard'))


@bp.route('/custom/<int:exam_id>')
def custom_link(exam_id):
    """Public link to check if a custom test is active or expired.
    Returns an informative page indicating status. Optionally can be extended to start the test.
    """
    ensure_customtest_details_column()
    exam = Exam.query.get_or_404(exam_id)
    from app.models import CustomTest
    custom_test = CustomTest.query.filter_by(exam_id=exam.id).first()
    refresh_and_persist_custom_test_status(custom_test)
    now = datetime.utcnow()
    status = 'active'
    starts_in = None
    expired = False
    if custom_test:
        if custom_test.started_at and now < custom_test.started_at:
            status = 'scheduled'
            starts_in = custom_test.started_at
        if custom_test.closed_at and now >= custom_test.closed_at:
            status = 'inactive'
            expired = True
    return render_template('exam/custom_link_status.html', exam=exam, custom_test=custom_test, status=status, starts_in=starts_in, expired=expired)
"""
Exam Blueprint Routes - Exam taking and management
"""

from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.exam import bp
from app.models import db, Subject, Topic, Question, Exam, ExamSession
from app import csrf
import random
from datetime import datetime, timedelta
import time
from sqlalchemy.orm import sessionmaker
import os
import json

from flask import current_app

@bp.route('/materials')
def study_materials():
    base_dir = os.path.join(current_app.static_folder, 'materials')  # FIXED ✅

    materials = {}
    for class_dir in os.listdir(base_dir):
        class_path = os.path.join(base_dir, class_dir)
        if os.path.isdir(class_path):
            materials[class_dir] = {}
            for subject in os.listdir(class_path):
                subject_path = os.path.join(class_path, subject)
                if os.path.isdir(subject_path):
                    videos = []
                    notes = []

                    videos_path = os.path.join(subject_path, 'videos')
                    notes_path = os.path.join(subject_path, 'notes')

                    if os.path.isdir(videos_path):
                        for v in os.listdir(videos_path):
                            if v.endswith('.mp4'):
                                videos.append(f'materials/{class_dir}/{subject}/videos/{v}')

                    if os.path.isdir(notes_path):
                        for n in os.listdir(notes_path):
                            if n.endswith('.pdf'):
                                notes.append(f'materials/{class_dir}/{subject}/notes/{n}')

                    materials[class_dir][subject.capitalize()] = {
                        'videos': videos,
                        'notes': notes
                    }

    return render_template('main/materials.html', materials=materials)


@bp.route('/dashboard')
@login_required
def dashboard():
    """Exam dashboard showing user's progress and available exams"""
    recent_sessions = ExamSession.query.filter_by(user_id=current_user.id)\
                                      .order_by(ExamSession.start_time.desc())\
                                      .limit(5).all()
    
    total_sessions = ExamSession.query.filter_by(user_id=current_user.id).count()
    avg_score = db.session.query(db.func.avg(ExamSession.percentage))\
                         .filter_by(user_id=current_user.id).scalar() or 0
    
    return render_template('exam/dashboard.html',
                         recent_sessions=recent_sessions,
                         total_sessions=total_sessions,
                         avg_score=round(avg_score, 1))

@bp.route('/practice')
def practice():
    """Practice page showing all subjects and topics"""
    subjects = Subject.query.all()
    return render_template('exam/practice.html', subjects=subjects)

@bp.route('/practice/topic/<int:topic_id>')
def practice_topic(topic_id):
    """Practice questions from a specific topic"""
    topic = Topic.query.get_or_404(topic_id)
    return render_template('exam/practice_topic.html', topic=topic)

@bp.route('/test/topic/<int:topic_id>')
@login_required
def topic_test(topic_id):
    """Create a timed test for a specific topic"""
    topic = Topic.query.get_or_404(topic_id)
    return render_template('exam/topic_test.html', topic=topic)


def is_exam_link_active(custom_test):
    """Utility to check if a custom test link is active based on start/end times"""
    if not custom_test:
        return True
    now = datetime.utcnow()
    if custom_test.started_at and now < custom_test.started_at:
        return False
    if custom_test.closed_at and now >= custom_test.closed_at:
        return False
    return True


@bp.route('/active-tests')
@login_required
def active_tests():
    """List active custom tests available for students to take"""
    try:
        ensure_customtest_details_column()
        from app.models import CustomTest
        # Determine current student's class level (if student)
        user_class_level = None
        try:
            if getattr(current_user, 'role', None) == 'student' and getattr(current_user, 'student_class', None):
                user_class_level = current_user.student_class.class_level
        except Exception:
            user_class_level = None
        # Fetch recent custom tests and filter by active window
        all_custom_tests = CustomTest.query.order_by(CustomTest.created_at.desc()).all()
        active_items = []
        now = datetime.utcnow()
        for ct in all_custom_tests:
            refresh_and_persist_custom_test_status(ct)
            # Derive real-time status using window
            status = 'active'
            if ct.started_at and now < ct.started_at:
                status = 'scheduled'
            if ct.closed_at and now >= ct.closed_at:
                status = 'inactive'
            if status != 'active':
                continue
            exam_obj = Exam.query.get(ct.exam_id) if ct.exam_id else None
            if not exam_obj:
                continue
            subject_obj = Subject.query.get(exam_obj.subject_id) if exam_obj else None
            # If user is a student, only show tests for their class level
            if user_class_level and subject_obj and subject_obj.class_level != user_class_level:
                continue
            # If user is a student, hide tests already attempted
            try:
                if user_class_level and ExamSession.query.filter_by(user_id=current_user.id, exam_id=exam_obj.id).first():
                    continue
            except Exception:
                pass
            # Only list tests that have configured question order OR attached questions
            try:
                showable = False
                details = None
                if hasattr(ct, 'details_json') and ct.details_json:
                    details = json.loads(ct.details_json)
                    ordered_ids = details.get('ordered_question_ids', []) or []
                    if len(ordered_ids) > 0:
                        showable = True
                if not showable:
                    # As a fallback, show if there are attached questions (if relationship exists)
                    if hasattr(exam_obj, 'questions') and exam_obj.questions:
                        showable = True
                if not showable:
                    continue
            except Exception:
                continue
            active_items.append({
                'custom_test_id': ct.id,
                'exam_id': exam_obj.id,
                'title': exam_obj.title or f"Custom Test #{ct.id}",
                'subject_name': subject_obj.name if subject_obj else 'Unknown',
                'class_level': subject_obj.class_level if subject_obj else '-',
                'duration_minutes': exam_obj.duration_minutes,
                'start_time': ct.started_at,
                'end_time': ct.closed_at,
                'creator': ct.created_by_username
            })
        return render_template('exam/active_tests.html', active_tests=active_items)
    except Exception as e:
        current_app.logger.error(f"Error loading active tests: {e}")
        flash('Could not load active tests right now.', 'error')
        return redirect(url_for('main.dashboard'))


@bp.route('/take-test/<int:exam_id>')
@login_required
def take_test(exam_id):
    """Render the test-taking UI for a specific active custom test"""
    try:
        ensure_customtest_details_column()
        exam = Exam.query.get_or_404(exam_id)
        # If user is a student, enforce class-level access to the test
        try:
            if getattr(current_user, 'role', None) == 'student' and getattr(current_user, 'student_class', None):
                user_class_level = current_user.student_class.class_level
                subj = Subject.query.get(exam.subject_id)
                if subj and subj.class_level != user_class_level:
                    flash('You are not authorized to take tests for this class.', 'error')
                    return redirect(url_for('exam.active_tests'))
        except Exception:
            pass
        from app.models import CustomTest
        custom_test = CustomTest.query.filter_by(exam_id=exam.id).first()
        refresh_and_persist_custom_test_status(custom_test)
        # Enforce active window
        if custom_test and not is_exam_link_active(custom_test):
            flash('This test is not currently active.', 'warning')
            return redirect(url_for('exam.active_tests'))

        # Enforce single attempt per student per test
        try:
            if ExamSession.query.filter_by(user_id=current_user.id, exam_id=exam_id).first():
                flash('You have already taken this test. Only one attempt is allowed.', 'info')
                return redirect(url_for('exam.results'))
        except Exception:
            pass

        # Determine ordered question IDs (from details_json) or fallback to attached exam.questions if available
        ordered_ids = []
        try:
            details_json = getattr(custom_test, 'details_json', None)
            if details_json:
                details = json.loads(details_json)
                ordered_ids = details.get('ordered_question_ids', [])
        except Exception as e:
            current_app.logger.warning(f"Failed to parse details_json for CustomTest {custom_test.id if custom_test else 'N/A'}: {e}")

        questions = []
        if ordered_ids:
            q_map = {q.id: q for q in Question.query.filter(Question.id.in_(ordered_ids)).all()}
            for qid in ordered_ids:
                q = q_map.get(int(qid))
                if q:
                    questions.append(q)
        else:
            # Fallback: try to load questions via Exam relationship if present
            try:
                if hasattr(exam, 'questions') and exam.questions:
                    # exam.questions may be a dynamic relationship; coerce to list and keep DB insertion order
                    questions = list(exam.questions)
                else:
                    raise AttributeError('Exam has no attached questions')
            except Exception:
                flash('This test is not properly configured yet. Please contact your teacher.', 'warning')
                return redirect(url_for('exam.active_tests'))

        subject = Subject.query.get(exam.subject_id)
        return render_template('exam/take_test.html', exam=exam, subject=subject, questions=questions, custom_test=custom_test)
    except Exception as e:
        current_app.logger.error(f"Error preparing test {exam_id}: {e}")
        flash('Could not start the test.', 'error')
        return redirect(url_for('exam.active_tests'))

@bp.route('/test/subject/<int:subject_id>')
@login_required
def subject_test(subject_id):
    """Create a comprehensive test for a subject"""
    subject = Subject.query.get_or_404(subject_id)
    return render_template('exam/subject_test.html', subject=subject)

@bp.route('/test/custom')
@login_required
def custom_test():
    """Create a custom test"""
    subjects = Subject.query.all()
    return render_template('exam/custom_test.html', subjects=subjects)

@bp.route('/results')
@login_required
def results():
    """Show user's exam results and analytics"""
    from sqlalchemy import func
    
    # Get all user sessions with eager loading
    try:
        # Force database query to refresh completely
        db.session.remove()
        
        # Get a fresh session count first to verify data freshness
        fresh_count = ExamSession.query.filter_by(user_id=current_user.id).count()
        current_app.logger.info(f"Fresh session count for user {current_user.id}: {fresh_count}")
        
        # Small delay to ensure any concurrent transactions complete
        time.sleep(0.5)
        
        # Create a new session to ensure fresh data
        Session = sessionmaker(bind=db.engine)
        fresh_session = Session()
        
        # Get all sessions for the current user, ordered by most recent first
        # Use eager loading to avoid DetachedInstanceError
        from sqlalchemy.orm import joinedload
        sessions = fresh_session.query(ExamSession).options(joinedload(ExamSession.exam))\
                                .filter_by(user_id=current_user.id)\
                                .order_by(ExamSession.start_time.desc()).all()
        
        # Create a list with exam titles loaded to avoid DetachedInstanceError
        sessions_with_exam_titles = []
        for session in sessions:
            # Create a wrapper object that mimics ExamSession interface
            class SessionWrapper:
                def __init__(self, session_data, exam_title):
                    self.id = session_data.id
                    self.start_time = session_data.start_time
                    self.end_time = session_data.end_time
                    self.duration_seconds = session_data.duration_seconds
                    self.score = session_data.score
                    self.max_score = session_data.max_score
                    self.percentage = session_data.percentage
                    self.status = session_data.status
                    self.questions_data = session_data.questions_data
                    self.exam_title = exam_title
                    self.exam = None  # Set to None to avoid accessing relationship
                    
                def get_questions_data(self):
                    if not self.questions_data:
                        return {}
                    try:
                        return json.loads(self.questions_data)
                    except json.JSONDecodeError:
                        return {}
            
            session_wrapper = SessionWrapper(session, session.exam.title if session.exam else 'Practice Test')
            sessions_with_exam_titles.append(session_wrapper)
        
        # Use the session wrappers instead of ORM objects
        sessions = sessions_with_exam_titles
        
        # Calculate analytics
        total_sessions = len(sessions)
        
        # Calculate average score safely
        if total_sessions > 0:
            valid_scores = [session.percentage for session in sessions if session.percentage is not None]
            avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        else:
            avg_score = 0
        
        # Print debug info
        current_app.logger.info(f"User ID: {current_user.id}")
        current_app.logger.info(f"Total sessions: {total_sessions}")
        current_app.logger.info(f"Average score: {avg_score}")
        if sessions:
            for session in sessions[:3]:  # First 3 sessions
                current_app.logger.info(f"Session {session.id}: {session.percentage}% score, {session.duration_seconds} seconds, Time: {session.start_time}")
        
        # Close the fresh session
        fresh_session.close()
    except Exception as e:
        current_app.logger.error(f"Error retrieving sessions: {str(e)}")
        import traceback
        traceback.print_exc()
        sessions = []
        total_sessions = 0
        avg_score = 0
    
    # Get best and worst performances
    try:
        best_session = max([s for s in sessions if s.percentage is not None], 
        key=lambda x: x.percentage) if sessions else None
    except (ValueError, AttributeError) as e:
        print(f"Error getting best session: {str(e)}")
        best_session = None

    # Calculate subject-wise performance
    try:
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                          'moderate': {'total': 0, 'correct': 0}, 
                          'difficult': {'total': 0, 'correct': 0}}
    except Exception as e:
        print(f"Error initializing stats: {str(e)}")
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                'moderate': {'total': 0, 'correct': 0}, 
                'difficult': {'total': 0, 'correct': 0}}
    except (ValueError, AttributeError) as e:
        print(f"Error getting best session: {str(e)}")
        best_session = None
        
    try:
        worst_session = min([s for s in sessions if s.percentage is not None], 
                           key=lambda x: x.percentage) if sessions else None
    except (ValueError, AttributeError) as e:
        print(f"Error getting worst session: {str(e)}")
        worst_session = None
    
    # Calculate subject-wise performance
    try:
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                          'moderate': {'total': 0, 'correct': 0}, 
                          'difficult': {'total': 0, 'correct': 0}}
    except Exception as e:
        print(f"Error initializing stats: {str(e)}")
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                'moderate': {'total': 0, 'correct': 0}, 
                'difficult': {'total': 0, 'correct': 0}}
    
    for session in sessions:
        questions_data = session.get_questions_data()
        questions = questions_data.get('questions', [])
        
        for question in questions:
            # Get question details for analysis
            try:
                question_id = question.get('question_id')
                if not question_id:
                    print(f"Warning: Question missing question_id in session {session.id}")
                    continue
                    
                q = Question.query.get(question_id)
                if q and q.topic:
                    # Subject stats
                    subject_name = q.topic.subject.name
                    if subject_name not in subject_stats:
                        subject_stats[subject_name] = {'total': 0, 'correct': 0, 'percentage': 0}
                    
                    subject_stats[subject_name]['total'] += 1
                    if question.get('is_correct'):
                        subject_stats[subject_name]['correct'] += 1
                    
                    # Topic stats
                    topic_name = q.topic.name
                    if topic_name not in topic_stats:
                        topic_stats[topic_name] = {'total': 0, 'correct': 0, 'percentage': 0, 'subject': subject_name}
                    
                    topic_stats[topic_name]['total'] += 1
                    if question.get('is_correct'):
                        topic_stats[topic_name]['correct'] += 1
                    
                    # Difficulty stats
                    difficulty = q.difficulty_level.lower() if q.difficulty_level else 'moderate'
                    if difficulty in difficulty_stats:
                        difficulty_stats[difficulty]['total'] += 1
                        if question.get('is_correct'):
                            difficulty_stats[difficulty]['correct'] += 1
                elif q:
                    print(f"Warning: Question {q.id} has no topic")
                else:
                    print(f"Warning: Question with ID {question_id} not found")
            except Exception as e:
                print(f"Error processing question in session {session.id}: {str(e)}")
    
    # Calculate percentages
    for subject in subject_stats.values():
        subject['percentage'] = (subject['correct'] / subject['total'] * 100) if subject['total'] > 0 else 0
    
    for topic in topic_stats.values():
        topic['percentage'] = (topic['correct'] / topic['total'] * 100) if topic['total'] > 0 else 0
    
    for difficulty in difficulty_stats.values():
        difficulty['percentage'] = (difficulty['correct'] / difficulty['total'] * 100) if difficulty['total'] > 0 else 0
    
    # Get recent sessions (last 5)
    recent_sessions = sessions[:5] if sessions else []
    
    # Performance trend (last 10 sessions)
    trend_sessions = sessions[:10] if sessions else []
    performance_trend = [{'date': session.start_time.strftime('%m/%d'), 
                         'percentage': session.percentage} for session in reversed(trend_sessions)]
    
    # Use results.html template for all cases - we've improved the AJAX refresh functionality
    current_app.logger.info(f"Using results.html template for all cases")
    
    # If ?format=json or Accept: application/json, return JSON
    if request.args.get('format') == 'json' or request.headers.get('Accept', '').startswith('application/json'):
        def session_to_dict(session):
            return {
                'id': getattr(session, 'id', None),
                'exam_title': getattr(session, 'exam_title', None),
                'start_time': session.start_time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(session, 'start_time') and session.start_time else None,
                'percentage': getattr(session, 'percentage', None),
                'score': getattr(session, 'score', None),
                'max_score': getattr(session, 'max_score', None),
                'duration_seconds': getattr(session, 'duration_seconds', None),
            }
        return jsonify({
            'sessions': [session_to_dict(s) for s in sessions],
            'recent_sessions': [session_to_dict(s) for s in recent_sessions],
            'total_sessions': total_sessions,
            'avg_score': round(avg_score, 1),
            'best_session': session_to_dict(best_session) if best_session else None,
            'worst_session': session_to_dict(worst_session) if worst_session else None,
            'subject_stats': subject_stats,
            'topic_stats': topic_stats,
            'difficulty_stats': difficulty_stats,
            'performance_trend': performance_trend
        })
    else:
        return render_template('exam/results.html', 
                             sessions=sessions,
                             recent_sessions=recent_sessions,
                             total_sessions=total_sessions,
                             avg_score=round(avg_score, 1),
                             best_session=best_session,
                             worst_session=worst_session,
                             subject_stats=subject_stats,
                             topic_stats=topic_stats,
                             difficulty_stats=difficulty_stats,
                             performance_trend=performance_trend)


@bp.route('/results/data', methods=['GET'])
@login_required
def results_data():
    """API endpoint to get user's analytics data for AJAX refresh"""
    from sqlalchemy import func
    
    try:
        current_app.logger.info(f"Results data API called by user {current_user.id}")
        
        # Force database query to refresh completely
        db.session.remove()
        
        # Create a new session to ensure fresh data
        Session = sessionmaker(bind=db.engine)
        fresh_session = Session()
        current_app.logger.info(f"Fresh database session created")
        
        # Get all sessions for the current user, ordered by most recent first
        # Use eager loading to avoid DetachedInstanceError
        from sqlalchemy.orm import joinedload
        sessions = fresh_session.query(ExamSession).options(joinedload(ExamSession.exam))\
                              .filter_by(user_id=current_user.id)\
                              .order_by(ExamSession.start_time.desc()).all()
        
        # Force loading of exam relationships while session is still active
        for session in sessions:
            if session.exam:
                _ = session.exam.title  # Access exam title to force loading
        
        # Calculate analytics
        total_sessions = len(sessions)
        
        # Calculate average score safely
        if total_sessions > 0:
            valid_scores = [session.percentage for session in sessions if session.percentage is not None]
            avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
        else:
            avg_score = 0
            
        # Get best session
        best_session = None
        if sessions:
            try:
                best_session = max([s for s in sessions if s.percentage is not None], 
                                  key=lambda x: x.percentage)
                best_session = {
                    'id': best_session.id,
                    'percentage': best_session.percentage,
                    'score': float(best_session.score) if best_session.score else 0,
                    'max_score': float(best_session.max_score) if best_session.max_score else 0
                }
                current_app.logger.info(f"Best session found: {best_session}")
            except (ValueError, AttributeError) as e:
                current_app.logger.error(f"Error getting best session: {str(e)}")
                
        # Calculate subject and topic stats
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {'easy': {'total': 0, 'correct': 0}, 
                          'moderate': {'total': 0, 'correct': 0}, 
                          'difficult': {'total': 0, 'correct': 0}}
        
        # Process each session
        for session in sessions:
            questions_data = session.get_questions_data()
            questions = questions_data.get('questions', [])
            current_app.logger.debug(f"Session {session.id} has {len(questions)} questions")
            
            for question in questions:
                try:
                    question_id = question.get('question_id')
                    if not question_id:
                        continue
                        
                    q = fresh_session.query(Question).get(question_id)
                    if q and q.topic:
                        # Subject stats
                        subject_name = q.topic.subject.name
                        if subject_name not in subject_stats:
                            subject_stats[subject_name] = {'total': 0, 'correct': 0, 'percentage': 0}
                        
                        subject_stats[subject_name]['total'] += 1
                        if question.get('is_correct'):
                            subject_stats[subject_name]['correct'] += 1
                        
                        # Topic stats
                        topic_name = q.topic.name
                        if topic_name not in topic_stats:
                            topic_stats[topic_name] = {'total': 0, 'correct': 0, 'percentage': 0, 'subject': subject_name}
                        
                        topic_stats[topic_name]['total'] += 1
                        if question.get('is_correct'):
                            topic_stats[topic_name]['correct'] += 1
                        
                        # Difficulty stats
                        difficulty = q.difficulty_level.lower() if q.difficulty_level else 'moderate'
                        if difficulty in difficulty_stats:
                            difficulty_stats[difficulty]['total'] += 1
                            if question.get('is_correct'):
                                difficulty_stats[difficulty]['correct'] += 1
                except Exception as e:
                    current_app.logger.error(f"Error processing question in session {session.id}: {str(e)}")
        
        # Calculate percentages
        for subject in subject_stats.values():
            subject['percentage'] = (subject['correct'] / subject['total'] * 100) if subject['total'] > 0 else 0
        
        for topic in topic_stats.values():
            topic['percentage'] = (topic['correct'] / topic['total'] * 100) if topic['total'] > 0 else 0
        
        for difficulty in difficulty_stats.values():
            difficulty['percentage'] = (difficulty['correct'] / difficulty['total'] * 100) if difficulty['total'] > 0 else 0
        
        # Performance trend (last 10 sessions)
        trend_sessions = sessions[:10] if sessions else []
        performance_trend = [{'date': session.start_time.strftime('%m/%d'), 
                             'percentage': session.percentage} for session in reversed(trend_sessions)]
        
        # Get recent sessions
        recent_sessions_data = []
        session_list_data = []
        
        for session in sessions:
            session_data = {
                'id': session.id,
                'start_time': session.start_time.strftime('%B %d, %Y at %I:%M %p'),
                'start_time_short': session.start_time.strftime('%b %d, %Y'),
                'percentage': float(session.percentage) if session.percentage is not None else 0.0,
                'score': int(session.score) if session.score else 0,
                'max_score': int(session.max_score) if session.max_score else 0,
                'duration_seconds': session.duration_seconds,
                'minutes': int(session.duration_seconds // 60) if session.duration_seconds else 0,
                'seconds': int(session.duration_seconds % 60) if session.duration_seconds else 0,
                'exam_title': session.exam.title if session.exam else 'Practice Test'
            }
            
            # Add to the list of all sessions
            session_list_data.append(session_data)
            
            # Also add to recent sessions if it's in the first 5
            if len(recent_sessions_data) < 5:
                recent_sessions_data.append(session_data)
        
        # Close the fresh session
        fresh_session.close()
        
        # Prepare response data
        response_data = {
            'total_sessions': total_sessions,
            'avg_score': round(avg_score, 1),
            'best_session': best_session,
            'subject_stats': subject_stats,
            'topic_stats': topic_stats,
            'difficulty_stats': difficulty_stats,
            'performance_trend': performance_trend,
            'recent_sessions': recent_sessions_data,
            'sessions': session_list_data,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        current_app.logger.info(f"Returning analytics data: total_sessions={total_sessions}, avg_score={avg_score}")
        
        # Return JSON data with appropriate headers
        response = jsonify(response_data)
        response.headers.add('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error getting analytics data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'total_sessions': 0,
            'avg_score': 0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@bp.route('/api/questions/random', methods=['POST'])
def api_get_random_questions():
    """API endpoint to get random questions for practice/test"""
    data = request.get_json()
    topic_id = data.get('topic_id')
    subject_id = data.get('subject_id')
    count = data.get('count', 10)
    difficulty = data.get('difficulty')
    
    query = Question.query
    
    if topic_id:
        query = query.filter_by(topic_id=topic_id)
    elif subject_id:
        # Get questions from all topics in the subject
        topic_ids = [t.id for t in Topic.query.filter_by(subject_id=subject_id).all()]
        query = query.filter(Question.topic_id.in_(topic_ids))
    
    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)
    
    # Get random questions
    total = query.count()
    if total == 0:
        return jsonify({'error': 'No questions found'}), 404
    
    # Use random sampling
    if total <= count:
        questions = query.all()
    else:
        # Get random offset
        random_offset = random.randint(0, max(0, total - count))
        questions = query.offset(random_offset).limit(count).all()
        
        # If we didn't get enough, get more from the beginning
        if len(questions) < count:
            remaining = count - len(questions)
            additional = query.limit(remaining).all()
            questions.extend(additional)
    
    # Format questions for response
    questions_data = []
    for q in questions:
        topic = Topic.query.get(q.topic_id)
        subject = Subject.query.get(topic.subject_id) if topic else None
        
        question_data = {
            'id': q.id,
            'qid': q.qid,
            'question': q.question_text,
            'options': q.get_options(),
            'correct_answer': q.correct_answer,
            'explanation': q.explanation,
            'difficulty_level': q.difficulty_level,
            'max_marks': q.max_marks,
            'topic': {
                'id': topic.id,
                'name': topic.name
            } if topic else None,
            'subject': {
                'id': subject.id,
                'name': subject.name,
                'class_level': subject.class_level
            } if subject else None
        }
        questions_data.append(question_data)
    
    return jsonify({
        'questions': questions_data,
        'total': len(questions_data)
    })

@bp.route('/submit-test', methods=['GET', 'POST'])
@login_required
def submit_test():
    """Enhanced test submission with comprehensive analytics and navigation"""
    if request.method == 'GET':
        # Get session ID from query params
        session_id = request.args.get('session_id')
        if not session_id:
            flash('Invalid session ID', 'error')
            return redirect(url_for('exam.dashboard'))
        
        session = ExamSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
        
        # Get questions data
        questions_data = session.get_questions_data()
        questions = questions_data.get('questions', [])
        test_info = questions_data.get('test_info', {})
        
        # Calculate comprehensive analytics
        analytics = calculate_comprehensive_analytics(session, questions)
        
        # Get comparative data with other students
        comparative_data = get_comparative_analytics(session)
        
        return render_template('exam/submit_test_results.html', 
                             session=session, 
                             questions=questions,
                             test_info=test_info,
                             analytics=analytics,
                             comparative_data=comparative_data)
    
    # POST method for form submissions (if needed)
    return redirect(url_for('exam.dashboard'))

@csrf.exempt
@bp.route('/api/submit-test', methods=['POST'])
@login_required
def api_submit_test():
    """Enhanced API endpoint to submit test answers and get comprehensive results"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        answers = data.get('answers', [])
        if not answers:
            return jsonify({'error': 'No answers provided'}), 400
            
        test_info = data.get('test_info', {})
        question_timings = data.get('question_timings', {})  # Time spent on each question
        navigation_data = data.get('navigation_data', {})    # Question navigation patterns
        
        print(f"Processing enhanced test submission with {len(answers)} answers")
        
        # Calculate score and detailed analytics (with marking scheme)
        total_questions = len(answers)
        correct_answers = 0
        wrong_answers = 0
        detailed_results = []
        attempted_questions = 0
        skipped_questions = 0
        difficulty_breakdown = {'easy': {'total': 0, 'correct': 0}, 
                              'moderate': {'total': 0, 'correct': 0}, 
                              'difficult': {'total': 0, 'correct': 0}}
        
        for i, answer_data in enumerate(answers):
            question_id = answer_data.get('question_id')
            user_answer = answer_data.get('answer', '')
            time_spent = question_timings.get(str(question_id), 0)
            is_attempted = answer_data.get('is_attempted', bool(user_answer))
            
            if not question_id:
                print(f"Warning: Answer at index {i} has no question_id")
                continue
                
            question = Question.query.get(question_id)
            if not question:
                print(f"Warning: Question with ID {question_id} not found")
                continue
            
            # Track attempt status
            if is_attempted:
                attempted_questions += 1
            else:
                skipped_questions += 1
                
            # Compare answers, handling case sensitivity and trimming whitespace
            is_correct = False
            if is_attempted and user_answer:
                is_correct = (question.correct_answer.strip().upper() == user_answer.strip().upper())
                if is_correct:
                    correct_answers += 1
                else:
                    wrong_answers += 1

            # Update difficulty breakdown (handle None safely)
            difficulty = (question.difficulty_level.lower() if question.difficulty_level else 'moderate')
            if difficulty in difficulty_breakdown:
                difficulty_breakdown[difficulty]['total'] += 1
                if is_correct:
                    difficulty_breakdown[difficulty]['correct'] += 1

            # Create enhanced detailed result for analytics
            detailed_results.append({
                'question_id': question_id,
                'question': question.question_text,
                'options': question.get_options(),
                'user_answer': user_answer,
                'correct_answer': question.correct_answer,
                'is_correct': is_correct,
                'is_attempted': is_attempted,
                'time_spent': time_spent,
                'explanation': question.explanation,
                'difficulty_level': question.difficulty_level if question.difficulty_level else 'moderate',
                'topic_id': question.topic_id,
                'topic_name': question.topic.name if question.topic else 'Unknown'
            })
        
        # Calculate comprehensive metrics
        # Determine marking scheme from test_info or CustomTest details
        positive_mark = 1
        negative_mark = 0
        # Ensure exam id is available early for inferring marking scheme
        passed_exam_id = None
        try:
            if isinstance(test_info, dict):
                passed_exam_id = test_info.get('exam_id')
        except Exception:
            passed_exam_id = None
        try:
            if isinstance(test_info, dict):
                ms = test_info.get('marking_scheme') or {}
                if isinstance(ms, dict):
                    if isinstance(ms.get('positive'), (int, float)):
                        positive_mark = int(ms.get('positive'))
                    if isinstance(ms.get('negative'), (int, float)):
                        negative_mark = int(ms.get('negative'))
            # If not provided, try to infer from CustomTest.details_json using exam_id
            if positive_mark == 1 and negative_mark == 0 and passed_exam_id:
                from app.models import CustomTest
                ct = CustomTest.query.filter_by(exam_id=passed_exam_id).first()
                if ct and getattr(ct, 'details_json', None):
                    try:
                        d = json.loads(ct.details_json)
                        ms2 = d.get('marking_scheme') or {}
                        if isinstance(ms2.get('positive'), (int, float)):
                            positive_mark = int(ms2.get('positive'))
                        if isinstance(ms2.get('negative'), (int, float)):
                            negative_mark = int(ms2.get('negative'))
                    except Exception:
                        pass
        except Exception:
            pass

        # Compute scored marks with negative marking
        score_marks = correct_answers * positive_mark - wrong_answers * negative_mark
        max_marks = total_questions * max(positive_mark, 1)
        if max_marks <= 0:
            max_marks = total_questions
        percentage = (score_marks / max_marks * 100) if max_marks > 0 else 0
        accuracy = (correct_answers / attempted_questions * 100) if attempted_questions > 0 else 0
        
        # Calculate timing metrics
        # Accept duration from either top-level or nested in test_info; ensure it's a non-negative int
        total_time = data.get('duration_seconds')
        if total_time is None:
            try:
                if isinstance(test_info, dict) and isinstance(test_info.get('duration_seconds'), (int, float)):
                    total_time = int(max(0, round(test_info.get('duration_seconds'))))
            except Exception:
                total_time = None
        if not isinstance(total_time, (int, float)):
            total_time = 0
        try:
            total_time = int(max(0, round(total_time)))
        except Exception:
            total_time = 0
        avg_time_per_question = total_time / total_questions if total_questions > 0 else 0
        
        print(f"Enhanced score calculation: {correct_answers}/{total_questions} = {percentage}%")
        print(f"Accuracy on attempted: {correct_answers}/{attempted_questions} = {accuracy}%")
        
        # Create enhanced exam session record
        # Use UTC for consistency across DB and displays
        end_time = datetime.utcnow()
        
        # Determine which exam this session belongs to
        exam_for_session = None
        if passed_exam_id:
            exam_for_session = Exam.query.get(passed_exam_id)
            # If there's a CustomTest for this exam, enforce schedule/expiry
            try:
                from app.models import CustomTest
                if exam_for_session:
                    ct = CustomTest.query.filter_by(exam_id=exam_for_session.id).first()
                    if ct:
                        now = datetime.utcnow()
                        if (ct.started_at and now < ct.started_at) or (ct.closed_at and now >= ct.closed_at):
                            return jsonify({'error': 'This test is not active.'}), 403
            except Exception:
                pass

        # If exam is determined, enforce single attempt per user per test
        try:
            if exam_for_session and ExamSession.query.filter_by(user_id=current_user.id, exam_id=exam_for_session.id).first():
                return jsonify({'error': 'You have already submitted this test. Only one attempt is allowed.'}), 403
        except Exception:
            pass

        if not exam_for_session:
            # Try to get or create a default practice exam
            # Robust subject_id detection
            subject_id_for_practice = None
            # 1. Try test_info
            if 'subject_id' in test_info:
                subject_id_for_practice = test_info['subject_id']
            # 2. Try request.form
            elif request.form.get('subject_id', type=int):
                subject_id_for_practice = request.form.get('subject_id', type=int)
            # 3. Try from questions/topics
            elif detailed_results and 'topic_id' in detailed_results[0]:
                topic_id = detailed_results[0]['topic_id']
                topic_obj = Topic.query.get(topic_id)
                if topic_obj:
                    subject_id_for_practice = topic_obj.subject_id
            # 4. Fallback to 1
            if not subject_id_for_practice:
                subject_id_for_practice = 1
            subject_obj = Subject.query.get(subject_id_for_practice)
            print(f"Practice session subject_id: {subject_id_for_practice}, subject: {subject_obj.name if subject_obj else 'Unknown'}")
            practice_exam = Exam.query.filter_by(title='Practice Test', subject_id=subject_id_for_practice).first()
            if not practice_exam:
                practice_exam = Exam(
                    title=f'Practice Test - {subject_obj.name if subject_obj else "Unknown"}',
                    description=f'Default practice exam for {subject_obj.name if subject_obj else "Unknown"}',
                    subject_id=subject_id_for_practice,
                    question_count=total_questions,
                    duration_minutes=30,
                    created_by=current_user.id
                )
                db.session.add(practice_exam)
                db.session.commit()
            exam_for_session = practice_exam

        session = ExamSession(
            user_id=current_user.id,
            exam_id=exam_for_session.id,
            score=score_marks,
            max_score=max_marks,
            percentage=percentage,
            status='completed',
            start_time=end_time - timedelta(seconds=total_time) if total_time else datetime.utcnow(),
            end_time=end_time,
            duration_seconds=total_time
        )
        
        # Store comprehensive session data
        session_data = {
            'questions': detailed_results,
            'test_info': test_info,
            'analytics': {
                'total_questions': total_questions,
                'attempted_questions': attempted_questions,
                'skipped_questions': skipped_questions,
                'correct_answers': correct_answers,
                'wrong_answers': wrong_answers,
                'marks': {
                    'positive': positive_mark,
                    'negative': negative_mark,
                    'score': score_marks,
                    'max': max_marks
                },
                'percentage': percentage,
                'accuracy': accuracy,
                'total_time': total_time,
                'avg_time_per_question': avg_time_per_question,
                'difficulty_breakdown': difficulty_breakdown
            },
            'navigation_data': navigation_data,
            'question_timings': question_timings
        }
        
        session.set_questions_data(session_data)
        
        # Save to database with retry logic
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                db.session.add(session)
                db.session.commit()
                print(f"Enhanced session saved with ID: {session.id}")
                
                # Ensure the database is refreshed with the new session
                db.session.refresh(session)
                success = True
            except Exception as db_error:
                retry_count += 1
                print(f"Database save attempt {retry_count} failed: {str(db_error)}")
                db.session.rollback()
                if retry_count >= max_retries:
                    raise db_error
                import time
                time.sleep(0.5)  # Wait before retrying

        # If this session belongs to a custom test, increment the taken count when applicable
        try:
            from app.models import CustomTest
            if session.exam_id:
                custom_test = CustomTest.query.filter_by(exam_id=session.exam_id).first()
                if custom_test:
                    # Refresh status based on time window
                    now = datetime.utcnow()
                    if custom_test.closed_at and now >= custom_test.closed_at:
                        custom_test.status = 'inactive'
                    elif custom_test.started_at and now < custom_test.started_at:
                        custom_test.status = 'scheduled'
                    else:
                        custom_test.status = 'active'

                    # Only count if active at submission time
                    if custom_test.status == 'active':
                        custom_test.number_of_students_taken = (custom_test.number_of_students_taken or 0) + 1
                    db.session.commit()
        except Exception as incr_err:
            current_app.logger.error(f"Failed to update CustomTest stats: {incr_err}")
        
        # Calculate comparative analytics
        comparative_data = get_comparative_analytics(session)
        
        return jsonify({
            'session_id': session.id,
            'score': score_marks,
            'total': max_marks,
            'percentage': round(percentage, 1),
            'accuracy': round(accuracy, 1),
            'attempted': attempted_questions,
            'skipped': skipped_questions,
            'correct': correct_answers,
            'wrong': wrong_answers,
            'marking_scheme': {
                'positive': positive_mark,
                'negative': negative_mark
            },
            'total_time': total_time,
            'avg_time_per_question': round(avg_time_per_question, 1),
            'difficulty_breakdown': difficulty_breakdown,
            'comparative_data': comparative_data,
            'results': detailed_results,
            'redirect_url': url_for('exam.submit_test', session_id=session.id)
        })
    except Exception as e:
        print(f"Error submitting enhanced test: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full stack trace for debugging
        db.session.rollback()  # Roll back any failed transaction
        
        # Provide more specific error messages
        if 'SQLite' in str(e) or 'database' in str(e).lower():
            return jsonify({'error': 'Database error occurred while saving. Please try again.'}), 500
        elif 'JSON' in str(e):
            return jsonify({'error': 'Invalid data format. Please try again.'}), 400
        else:
            return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/session/<int:session_id>/details')
@login_required
def session_details(session_id):
    """Show detailed session results with questions, answers, and explanations"""
    try:
        # Ensure we get fresh data with eager loading
        from sqlalchemy.orm import joinedload
        db.session.close()
        session = ExamSession.query.options(joinedload(ExamSession.exam))\
                                  .filter_by(id=session_id, user_id=current_user.id).first_or_404()
        
        print(f"Retrieving details for session ID: {session_id}")
        
        # Get questions data from session
        questions_data = session.get_questions_data()
        questions = questions_data.get('questions', [])
        test_info = questions_data.get('test_info', {})
        
        print(f"DEBUG: Raw questions_data: {questions_data}")
        print(f"DEBUG: Questions list length: {len(questions)}")
        print(f"DEBUG: Test info: {test_info}")
        
        if not questions:
            print(f"Warning: No questions found in session {session_id}")
        
        # Fetch full question details with explanations
        detailed_questions = []
        for i, q_data in enumerate(questions):
            print(f"DEBUG: Processing question {i}: {q_data}")
            try:
                question_id = q_data.get('question_id')
                if not question_id:
                    print(f"Warning: Question {i} in session {session_id} has no question_id")
                    continue
                    
                question = Question.query.get(question_id)
                if question:
                    question_detail = {
                        'question': question,
                        'user_answer': q_data.get('user_answer'),
                        'correct_answer': q_data.get('correct_answer', question.correct_answer),
                        'is_correct': q_data.get('is_correct', False),
                        'explanation': q_data.get('explanation') or question.explanation or "No explanation available."
                    }
                    detailed_questions.append(question_detail)
                    print(f"DEBUG: Added question {i} to detailed_questions")
                else:
                    print(f"Warning: Question with ID {question_id} not found")
            except Exception as e:
                print(f"Error processing question {i} in session {session_id}: {str(e)}")
        
        print(f"DEBUG: Final detailed_questions length: {len(detailed_questions)}")
        print(f"DEBUG: Sample detailed_question: {detailed_questions[0] if detailed_questions else 'None'}")
        
        # Calculate correct answers
        correct_answers = sum(1 for q in detailed_questions if q.get('is_correct'))
        
        print(f"DEBUG: Correct answers count: {correct_answers}")
        print(f"DEBUG: Total questions: {len(detailed_questions)}")
        print(f"DEBUG: About to render template with:")
        print(f"  - session: {session.id if session else 'None'}")
        print(f"  - questions count: {len(detailed_questions)}")
        print(f"  - total_questions: {len(detailed_questions)}")
        print(f"  - correct_answers: {correct_answers}")
        print(f"  - test_info keys: {list(test_info.keys()) if test_info else 'None'}")
        
        # If session doesn't have a time, try to get it from test_info
        if not session.duration_seconds and test_info and 'duration_seconds' in test_info:
            session.duration_seconds = test_info['duration_seconds']
            # Save it to the database for future reference
            db.session.commit()
        
        return render_template('exam/session_details.html',
                             session=session,
                             questions=detailed_questions,
                             total_questions=len(detailed_questions),
                             correct_answers=correct_answers,
                             test_info=test_info)
    except Exception as e:
        print(f"Error retrieving session details for session {session_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error retrieving session details: {str(e)}", "danger")
        return redirect(url_for('exam.results'))


@bp.route('/session/<int:session_id>/details/teacher')
@login_required
def session_details_teacher(session_id):
    """Teacher view: detailed session results for any student"""
    try:
        if getattr(current_user, 'role', None) not in ('teacher', 'admin'):
            flash('Access denied: Only teachers or admins can view this page.', 'error')
            return redirect(url_for('main.dashboard'))

        from sqlalchemy.orm import joinedload
        db.session.close()
        session = ExamSession.query.options(joinedload(ExamSession.exam))\
                                  .filter_by(id=session_id).first_or_404()

        questions_data = session.get_questions_data()
        questions = questions_data.get('questions', [])
        test_info = questions_data.get('test_info', {})

        detailed_questions = []
        """
        for i, q_data in enumerate(questions):
            try:
                question_id = q_data.get('question_id')
                if not question_id:
                    continue
                question = q_data.get('question')
                if question:
                    detailed_questions.append({
                        'question': question,
                        'user_answer': q_data.get('user_answer'),
                        'correct_answer': q_data.get('correct_answer',''),
                        'is_correct': q_data.get('is_correct', False),
                        'explanation': q_data.get('explanation', "No explanation available.")
                    })
            except Exception:
                pass
                """
        for i, q_data in enumerate(questions):
            try:
                question_id = q_data.get('question_id')
                if not question_id:
                    continue
                question_obj = Question.query.get(question_id)
                if question_obj:
                    detailed_questions.append({
                        'question': question_obj,  # For options/explanation
                        'question_text': q_data.get('question', question_obj.question_text),  # For displaying the text
                        'user_answer': q_data.get('user_answer'),
                        'correct_answer': q_data.get('correct_answer', question_obj.correct_answer),
                        'is_correct': q_data.get('is_correct', False),
                        'explanation': q_data.get('explanation') or question_obj.explanation or "No explanation available."
                    })
            except Exception:
                pass

        correct_answers = sum(1 for q in detailed_questions if q.get('is_correct'))
        print("session:", session)
        print("questions:", questions)
        print("total_questions:", detailed_questions)
        print("correct_answers:", correct_answers)
        print("test_info:", test_info)

        return render_template('exam/session_details.html',
                             session=session,
                             questions=detailed_questions,
                             total_questions=len(detailed_questions),
                             correct_answers=correct_answers,
                             test_info=test_info,
                             test="teacher")
    except Exception as e:
        current_app.logger.error(f"Error retrieving teacher session details for {session_id}: {e}")
        flash('Could not load session details.', 'error')
        return redirect(url_for('main.dashboard'))


@bp.route('/custom/<int:exam_id>/submissions')
@login_required
def custom_test_submissions(exam_id):
    """Teacher view: list all student submissions for a specific custom test"""
    if getattr(current_user, 'role', None) not in ('teacher', 'admin'):
        flash('Access denied: Only teachers or admins can view submissions.', 'error')
        return redirect(url_for('main.dashboard'))
    try:
        from sqlalchemy.orm import joinedload
        exam = Exam.query.get_or_404(exam_id)
        sessions = ExamSession.query.options(joinedload(ExamSession.user))\
                                   .filter_by(exam_id=exam_id, status='completed')\
                                   .order_by(ExamSession.percentage.desc(), ExamSession.end_time.desc()).all()
        # Prepare display-friendly rows with accurate duration and ISO timestamps (UTC)
        sessions_info = []
        for rank, s in enumerate(sessions, 1):
            try:
                duration_seconds = int(s.duration_seconds or 0)
                # Fallbacks: compute from stored JSON or from timestamps
                if duration_seconds <= 0:
                    try:
                        data = s.get_questions_data()
                        analytics = data.get('analytics', {}) if isinstance(data, dict) else {}
                        ti = data.get('test_info', {}) if isinstance(data, dict) else {}
                        if isinstance(analytics.get('total_time'), (int, float)):
                            duration_seconds = int(analytics.get('total_time'))
                        elif isinstance(ti.get('duration_seconds'), (int, float)):
                            duration_seconds = int(ti.get('duration_seconds'))
                    except Exception:
                        pass
                if duration_seconds <= 0 and s.start_time and s.end_time:
                    duration_seconds = int(max(0, (s.end_time - s.start_time).total_seconds()))
            except Exception:
                duration_seconds = 0
            try:
                # Use UTC ISO for client-side localization
                end_iso = s.end_time.strftime('%Y-%m-%dT%H:%M:00') + 'Z' if s.end_time else ''
                end_str = end_iso
            except Exception:
                end_iso = ''
                end_str = ''
            sessions_info.append({
                'id': s.id,
                'rank': rank,
                'username': s.user.username if s.user else 'Unknown',
                'score': int(s.score or 0),
                'max_score': int(s.max_score or 0),
                'percentage': float(s.percentage or 0),
                'duration_seconds': duration_seconds,
                'end_time_str': end_str
            })
        return render_template('exam/custom_submissions.html', exam=exam, sessions=sessions_info)
    except Exception as e:
        current_app.logger.error(f"Error loading submissions for exam {exam_id}: {e}")
        flash('Could not load submissions.', 'error')
        return redirect(url_for('main.dashboard'))


@bp.route('/custom/<int:exam_id>/submissions/json')
@login_required
def custom_test_submissions_json(exam_id):
    """AJAX endpoint to get submissions data in JSON format for real-time updates"""
    if getattr(current_user, 'role', None) not in ('teacher', 'admin'):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        from sqlalchemy.orm import joinedload
        exam = Exam.query.get_or_404(exam_id)
        sessions = ExamSession.query.options(joinedload(ExamSession.user))\
                                   .filter_by(exam_id=exam_id, status='completed')\
                                   .order_by(ExamSession.percentage.desc(), ExamSession.end_time.desc()).all()
        
        sessions_data = []
        for rank, s in enumerate(sessions, 1):
            try:
                duration_seconds = int(s.duration_seconds or 0)
                if duration_seconds <= 0 and s.start_time and s.end_time:
                    duration_seconds = int(max(0, (s.end_time - s.start_time).total_seconds()))
            except Exception:
                duration_seconds = 0
                
            sessions_data.append({
                'id': s.id,
                'rank': rank,
                'username': s.user.username if s.user else 'Unknown',
                'score': int(s.score or 0),
                'max_score': int(s.max_score or 0),
                'percentage': float(s.percentage or 0),
                'duration_seconds': duration_seconds,
                'end_time_str': s.end_time.strftime('%Y-%m-%dT%H:%M:00Z') if s.end_time else ''
            })
        
        return jsonify({
            'exam_title': exam.title,
            'total_submissions': len(sessions_data),
            'sessions': sessions_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error loading submissions JSON for exam {exam_id}: {e}")
        return jsonify({'error': 'Could not load submissions'}), 500


@bp.route('/my-tests')
@login_required
def my_tests():
    """Teacher page: list all custom tests created by the current teacher"""
    if getattr(current_user, 'role', None) not in ('teacher', 'admin'):
        flash('Access denied: Only teachers or admins can view this page.', 'error')
        return redirect(url_for('main.dashboard'))
    try:
        ensure_customtest_details_column()
        from app.models import CustomTest
        tests = CustomTest.query.filter_by(created_by_user_id=current_user.id) \
                                 .order_by(CustomTest.created_at.desc()).all()
        items = []
        now = datetime.utcnow()
        for ct in tests:
            exam_obj = Exam.query.get(ct.exam_id) if ct.exam_id else None
            if not exam_obj:
                continue
            subject_obj = Subject.query.get(exam_obj.subject_id) if exam_obj else None
            # Compute live status based on window
            status = 'active'
            if ct.started_at and now < ct.started_at:
                status = 'scheduled'
            if ct.closed_at and now >= ct.closed_at:
                status = 'inactive'
            # Submissions count from sessions
            sessions_count = ExamSession.query.filter_by(exam_id=exam_obj.id, status='completed').count()
            items.append({
                'exam_id': exam_obj.id,
                'title': exam_obj.title,
                'subject_name': subject_obj.name if subject_obj else 'Unknown',
                'class_level': subject_obj.class_level if subject_obj else '-',
                'duration_minutes': exam_obj.duration_minutes,
                'status': status,
                'started_at': ct.started_at,
                'closed_at': ct.closed_at,
                'created_at': ct.created_at,
                'submissions': sessions_count,
                'link_url': url_for('exam.custom_link', exam_id=exam_obj.id),
                'submissions_url': url_for('exam.custom_test_submissions', exam_id=exam_obj.id)
            })
        return render_template('exam/my_tests.html', tests=items)
    except Exception as e:
        current_app.logger.error(f"Error loading my tests: {e}")
        flash('Could not load your tests.', 'error')
        return redirect(url_for('main.dashboard'))


@bp.route('/custom/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_custom_timings(exam_id):
    """Allow a teacher to edit the start/end timings for an active custom test."""
    if getattr(current_user, 'role', None) != 'teacher':
        flash('Access denied: Only teachers can edit test timings.', 'error')
        return redirect(url_for('main.dashboard'))
    try:
        ensure_customtest_details_column()
        from app.models import CustomTest
        exam = Exam.query.get_or_404(exam_id)
        custom_test = CustomTest.query.filter_by(exam_id=exam.id).first_or_404()

        if request.method == 'GET':
            # Prefill values formatted for datetime-local input
            def fmt(dt):
                return dt.strftime('%Y-%m-%dT%H:%M') if dt else ''
            return render_template(
                'exam/edit_custom_timings.html',
                exam=exam,
                custom_test=custom_test,
                start_value=fmt(custom_test.started_at),
                end_value=fmt(custom_test.closed_at)
            )

        # POST: update timings
        start_str = request.form.get('start_datetime')
        end_str = request.form.get('end_datetime')

        started_at = None
        closed_at = None
        try:
            if start_str:
                IST = timezone(timedelta(hours=5, minutes=30))
                started_local = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
                started_at = started_local.replace(tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            flash('Invalid start date/time format.', 'error')
            return redirect(url_for('exam.edit_custom_timings', exam_id=exam.id))
        try:
            if end_str:
                IST = timezone(timedelta(hours=5, minutes=30))
                closed_local = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')
                closed_at = closed_local.replace(tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            flash('Invalid end date/time format.', 'error')
            return redirect(url_for('exam.edit_custom_timings', exam_id=exam.id))

        # Validate ordering if both provided
        if started_at and closed_at and closed_at <= started_at:
            flash('End time must be after start time.', 'error')
            return redirect(url_for('exam.edit_custom_timings', exam_id=exam.id))

        # Update and set status
        custom_test.started_at = started_at
        custom_test.closed_at = closed_at
        now = datetime.utcnow()
        if started_at and now < started_at:
            custom_test.status = 'scheduled'
        elif closed_at and now >= closed_at:
            custom_test.status = 'inactive'
        else:
            custom_test.status = 'active'

        db.session.commit()
        flash('Test timings updated successfully.', 'success')
        return redirect(url_for('exam.custom_link', exam_id=exam.id))
    except Exception as e:
        current_app.logger.error(f"Failed to edit timings for exam {exam_id}: {e}")
        db.session.rollback()
        flash('Could not update test timings.', 'error')
        return redirect(url_for('exam.my_tests'))


@bp.route('/custom/clear-all', methods=['POST'])
@login_required
def clear_all_custom_tests():
    """Delete all custom tests created by the current teacher, including related exams and submissions."""
    if getattr(current_user, 'role', None) != 'teacher':
        flash('Access denied: Only teachers can clear tests.', 'error')
        return redirect(url_for('main.dashboard'))
    try:
        from app.models import CustomTest
        # Gather tests created by this teacher
        custom_tests = CustomTest.query.filter_by(created_by_user_id=current_user.id).all()
        if not custom_tests:
            flash('No custom tests to clear.', 'info')
            return redirect(url_for('exam.my_tests'))

        exam_ids = [ct.exam_id for ct in custom_tests if ct.exam_id]
        # Delete related exam sessions first
        if exam_ids:
            try:
                db.session.query(ExamSession).filter(ExamSession.exam_id.in_(exam_ids)).delete(synchronize_session=False)
            except Exception:
                # Fallback to per-row deletion for older SQLite versions
                for sid in exam_ids:
                    for sess in ExamSession.query.filter_by(exam_id=sid).all():
                        db.session.delete(sess)

        # Delete custom tests
        for ct in custom_tests:
            db.session.delete(ct)

        # Delete exams
        if exam_ids:
            try:
                db.session.query(Exam).filter(Exam.id.in_(exam_ids)).delete(synchronize_session=False)
            except Exception:
                for ex_id in exam_ids:
                    ex = Exam.query.get(ex_id)
                    if ex:
                        db.session.delete(ex)

        db.session.commit()
        flash(f'Cleared {len(custom_tests)} custom tests and related data.', 'success')
    except Exception as e:
        current_app.logger.error(f"Failed to clear custom tests: {e}")
        db.session.rollback()
        flash('Could not clear tests. Please try again.', 'error')
    return redirect(url_for('exam.my_tests'))


@bp.route('/delete-test/<int:exam_id>', methods=['POST'])
@login_required
def delete_test(exam_id):
    """Delete a custom test created by the current teacher"""
    if getattr(current_user, 'role', None) not in ('teacher', 'admin'):
        flash('Access denied: Only teachers or admins can delete tests.', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        from app.models import CustomTest
        
        # Find the exam and verify ownership
        exam = Exam.query.get_or_404(exam_id)
        custom_test = CustomTest.query.filter_by(exam_id=exam_id, created_by_user_id=current_user.id).first()
        
        if not custom_test:
            flash('Test not found or you do not have permission to delete it.', 'error')
            return redirect(url_for('exam.my_tests'))
        
        # Delete all related exam sessions first
        sessions_deleted = ExamSession.query.filter_by(exam_id=exam_id).delete()
        
        # Delete the custom test record
        db.session.delete(custom_test)
        
        # Delete the exam itself
        db.session.delete(exam)
        
        db.session.commit()
        
        flash(f'Test "{exam.title}" and {sessions_deleted} related submissions have been successfully deleted.', 'success')
        
    except Exception as e:
        current_app.logger.error(f"Error deleting test {exam_id}: {str(e)}")
        db.session.rollback()
        flash('Error deleting test. Please try again.', 'error')
    
    return redirect(url_for('exam.my_tests'))


@bp.route('/preview-test/<int:exam_id>')
@login_required
def preview_test(exam_id):
    """Preview a custom test created by the current teacher"""
    if getattr(current_user, 'role', None) not in ('teacher', 'admin'):
        flash('Access denied: Only teachers or admins can preview tests.', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        from app.models import CustomTest
        
        # Find the exam and verify ownership
        exam = Exam.query.get_or_404(exam_id)
        custom_test = CustomTest.query.filter_by(exam_id=exam_id, created_by_user_id=current_user.id).first()
        
        if not custom_test:
            flash('Test not found or you do not have permission to preview it.', 'error')
            return redirect(url_for('exam.my_tests'))
        
        # Get questions from the custom test's details_json field
        questions = []
        try:
            if custom_test.details_json:
                import json
                details = json.loads(custom_test.details_json)
                ordered_question_ids = details.get('ordered_question_ids', [])
                
                if ordered_question_ids:
                    # Get questions from database in the correct order
                    questions_dict = {q.id: q for q in Question.query.filter(Question.id.in_(ordered_question_ids)).all()}
                    questions = [questions_dict[qid] for qid in ordered_question_ids if qid in questions_dict]
                    
        except Exception as e:
            current_app.logger.error(f"Error parsing custom test details: {str(e)}")
        
        if not questions:
            flash('No questions found for this test.', 'error')
            return redirect(url_for('exam.my_tests'))
        
        # Get subject information
        subject = Subject.query.get(exam.subject_id) if exam.subject_id else None
        
        # Calculate current status
        now = datetime.utcnow()
        status = 'active'
        if custom_test.started_at and now < custom_test.started_at:
            status = 'scheduled'
        elif custom_test.closed_at and now >= custom_test.closed_at:
            status = 'inactive'
        
        return render_template('exam/preview_test.html', 
                             exam=exam, 
                             questions=questions, 
                             subject=subject,
                             custom_test=custom_test,
                             status=status)
        
    except Exception as e:
        current_app.logger.error(f"Error previewing test {exam_id}: {str(e)}")
        flash('Error loading test preview. Please try again.', 'error')
        return redirect(url_for('exam.my_tests'))


def calculate_comprehensive_analytics(session, questions):
    """Calculate comprehensive analytics for a test session"""
    from sqlalchemy import func
    
    analytics = {
        'question_status': {'attempted': 0, 'skipped': 0, 'correct': 0, 'incorrect': 0},
        'time_analysis': {'total_time': 0, 'avg_per_question': 0, 'fastest': float('inf'), 'slowest': 0},
        'difficulty_analysis': {'easy': {'total': 0, 'correct': 0, 'avg_time': 0},
                               'moderate': {'total': 0, 'correct': 0, 'avg_time': 0},
                               'difficult': {'total': 0, 'correct': 0, 'avg_time': 0}},
        'topic_analysis': {},
        'accuracy_trend': [],
        'speed_vs_accuracy': {'fast_correct': 0, 'fast_incorrect': 0, 'slow_correct': 0, 'slow_incorrect': 0}
    }
    
    # Get session data
    session_data = session.get_questions_data()
    question_timings = session_data.get('question_timings', {})
    total_time = session.duration_seconds or 0
    
    # Calculate question-level analytics
    for i, question in enumerate(questions):
        is_attempted = question.get('is_attempted', False)
        is_correct = question.get('is_correct', False)
        time_spent = question.get('time_spent', 0)
        difficulty = question.get('difficulty_level', 'moderate').lower()
        topic_name = question.get('topic_name', 'Unknown')
        
        # Question status
        if is_attempted:
            analytics['question_status']['attempted'] += 1
            if is_correct:
                analytics['question_status']['correct'] += 1
            else:
                analytics['question_status']['incorrect'] += 1
        else:
            analytics['question_status']['skipped'] += 1
        
        # Time analysis
        if time_spent > 0:
            analytics['time_analysis']['fastest'] = min(analytics['time_analysis']['fastest'], time_spent)
            analytics['time_analysis']['slowest'] = max(analytics['time_analysis']['slowest'], time_spent)
        
        # Difficulty analysis
        if difficulty in analytics['difficulty_analysis']:
            analytics['difficulty_analysis'][difficulty]['total'] += 1
            if is_correct:
                analytics['difficulty_analysis'][difficulty]['correct'] += 1
            if time_spent > 0:
                current_avg = analytics['difficulty_analysis'][difficulty]['avg_time']
                current_count = analytics['difficulty_analysis'][difficulty]['total']
                analytics['difficulty_analysis'][difficulty]['avg_time'] = (
                    (current_avg * (current_count - 1) + time_spent) / current_count
                )
        
        # Topic analysis
        if topic_name not in analytics['topic_analysis']:
            analytics['topic_analysis'][topic_name] = {'total': 0, 'correct': 0, 'avg_time': 0}
        analytics['topic_analysis'][topic_name]['total'] += 1
        if is_correct:
            analytics['topic_analysis'][topic_name]['correct'] += 1
        if time_spent > 0:
            current_avg = analytics['topic_analysis'][topic_name]['avg_time']
            current_count = analytics['topic_analysis'][topic_name]['total']
            analytics['topic_analysis'][topic_name]['avg_time'] = (
                (current_avg * (current_count - 1) + time_spent) / current_count
            )
        
        # Accuracy trend (correct answers up to this point)
        correct_so_far = sum(1 for q in questions[:i+1] if q.get('is_correct', False))
        analytics['accuracy_trend'].append({
            'question_number': i + 1,
            'accuracy': (correct_so_far / (i + 1)) * 100
        })
        
        # Speed vs Accuracy (using median time as threshold)
        if time_spent > 0:
            median_time = total_time / len(questions) if len(questions) > 0 else 0
            if time_spent <= median_time:  # Fast
                if is_correct:
                    analytics['speed_vs_accuracy']['fast_correct'] += 1
                else:
                    analytics['speed_vs_accuracy']['fast_incorrect'] += 1
            else:  # Slow
                if is_correct:
                    analytics['speed_vs_accuracy']['slow_correct'] += 1
                else:
                    analytics['speed_vs_accuracy']['slow_incorrect'] += 1
    
    # Finalize time analysis
    analytics['time_analysis']['total_time'] = total_time
    analytics['time_analysis']['avg_per_question'] = total_time / len(questions) if len(questions) > 0 else 0
    if analytics['time_analysis']['fastest'] == float('inf'):
        analytics['time_analysis']['fastest'] = 0
    
    # Calculate percentages for difficulty analysis
    for difficulty in analytics['difficulty_analysis']:
        if analytics['difficulty_analysis'][difficulty]['total'] > 0:
            analytics['difficulty_analysis'][difficulty]['accuracy'] = (
                analytics['difficulty_analysis'][difficulty]['correct'] / 
                analytics['difficulty_analysis'][difficulty]['total'] * 100
            )
        else:
            analytics['difficulty_analysis'][difficulty]['accuracy'] = 0
    
    # Calculate percentages for topic analysis
    for topic in analytics['topic_analysis']:
        if analytics['topic_analysis'][topic]['total'] > 0:
            analytics['topic_analysis'][topic]['accuracy'] = (
                analytics['topic_analysis'][topic]['correct'] / 
                analytics['topic_analysis'][topic]['total'] * 100
            )
        else:
            analytics['topic_analysis'][topic]['accuracy'] = 0
    
    return analytics


def get_comparative_analytics(session):
    """Get comparative analytics with other students"""
    from sqlalchemy import func
    
    comparative_data = {
        'user_percentile': 0,
        'avg_score_all_users': 0,
        'user_rank': 0,
        'total_participants': 0,
        'time_comparison': {'faster_than': 0, 'slower_than': 0},
        'difficulty_comparison': {'easy': {}, 'moderate': {}, 'difficult': {}}
    }
    
    try:
        # Get all completed sessions for comparison
        all_sessions = ExamSession.query.filter_by(status='completed').all()
        
        if not all_sessions:
            return comparative_data
        
        # Calculate basic comparisons
        user_score = session.percentage
        all_scores = [s.percentage for s in all_sessions if s.percentage is not None]
        
        if all_scores:
            comparative_data['avg_score_all_users'] = sum(all_scores) / len(all_scores)
            comparative_data['total_participants'] = len(all_scores)
            
            # Calculate percentile (percentage of students scored lower)
            lower_scores = [s for s in all_scores if s < user_score]
            comparative_data['user_percentile'] = (len(lower_scores) / len(all_scores)) * 100
            
            # Calculate rank
            sorted_scores = sorted(all_scores, reverse=True)
            user_rank = 1
            for i, score in enumerate(sorted_scores):
                if score <= user_score:
                    user_rank = i + 1
                    break
            comparative_data['user_rank'] = user_rank
        
        # Time comparison
        user_time = session.duration_seconds
        all_times = [s.duration_seconds for s in all_sessions if s.duration_seconds is not None]
        
        if all_times and user_time:
            faster_than = sum(1 for t in all_times if t > user_time)
            slower_than = sum(1 for t in all_times if t < user_time)
            comparative_data['time_comparison'] = {
                'faster_than': (faster_than / len(all_times)) * 100,
                'slower_than': (slower_than / len(all_times)) * 100
            }
        
        # Difficulty-wise comparison
        user_data = session.get_questions_data()
        user_difficulty_stats = user_data.get('analytics', {}).get('difficulty_breakdown', {})
        
        # Calculate average performance by difficulty across all users
        for difficulty in ['easy', 'moderate', 'difficult']:
            difficulty_scores = []
            for s in all_sessions:
                s_data = s.get_questions_data()
                s_analytics = s_data.get('analytics', {})
                s_difficulty = s_analytics.get('difficulty_breakdown', {}).get(difficulty, {})
                if s_difficulty.get('total', 0) > 0:
                    accuracy = (s_difficulty.get('correct', 0) / s_difficulty.get('total', 1)) * 100
                    difficulty_scores.append(accuracy)
            
            if difficulty_scores:
                avg_difficulty_score = sum(difficulty_scores) / len(difficulty_scores)
                user_difficulty_score = 0
                if user_difficulty_stats.get(difficulty, {}).get('total', 0) > 0:
                    user_difficulty_score = (
                        user_difficulty_stats[difficulty].get('correct', 0) / 
                        user_difficulty_stats[difficulty].get('total', 1) * 100
                    )
                
                comparative_data['difficulty_comparison'][difficulty] = {
                    'user_score': user_difficulty_score,
                    'average_score': avg_difficulty_score,
                    'above_average': user_difficulty_score > avg_difficulty_score
                }
    
    except Exception as e:
        print(f"Error calculating comparative analytics: {str(e)}")
    
    return comparative_data

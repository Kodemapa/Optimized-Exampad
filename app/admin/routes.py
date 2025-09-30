
"""
Admin Routes - Administrative dashboard and analytics
"""

from flask import render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.admin import bp
from app.models import db, User, Subject, Topic, Question, Exam, ExamSession, CustomTest, SiteSetting
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta
import json
def admin_required(f):
    """Decorator to require admin or superadmin role"""
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role not in ('admin', 'superadmin')):
            flash('Admin access required', 'error')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@bp.route('/all-submissions')
@login_required
@admin_required
def all_submissions():
    # Get all exams
    exams = Exam.query.order_by(Exam.created_at.desc()).all()
    exam_list = []
    for exam in exams:
        subject = Subject.query.get(exam.subject_id) if exam.subject_id else None
        teacher = User.query.get(exam.created_by) if exam.created_by else None
        submissions = ExamSession.query.filter_by(exam_id=exam.id, status='completed').count()
        exam_list.append({
            'id': exam.id,
            'title': exam.title,
            'subject': subject.name if subject else 'Unknown',
            'teacher': teacher.username if teacher else 'Unknown',
            'created_at': exam.created_at,
            'submissions': submissions
        })
    return render_template('admin/all_submissions.html', exams=exam_list)

# Note: admin_required defined above; duplicate removed to avoid redefinition.


# Admin: Custom Tests Overview (list all teachers and their active tests)
@bp.route('/custom-tests')
@login_required
@admin_required
def custom_tests():
    # Get all users with teacher role
    teachers = User.query.filter_by(role='teacher').all()
    teacher_data = []
    for t in teachers:
        active_tests = CustomTest.query.filter_by(created_by_user_id=t.id, status='active').count()
        teacher_data.append({
            'id': t.id,
            'username': t.username,
            'active_tests': active_tests
        })
    return render_template('admin/custom_tests.html', teachers=teacher_data)


# Admin: View all tests by a specific teacher
@bp.route('/custom-tests/<int:teacher_id>')
@login_required
@admin_required
def view_teacher_tests(teacher_id):
    teacher = User.query.get_or_404(teacher_id)
    # Get all custom tests created by this teacher
    tests = CustomTest.query.filter_by(created_by_user_id=teacher.id).order_by(CustomTest.created_at.desc()).all()
    test_items = []
    for ct in tests:
        exam_obj = Exam.query.get(ct.exam_id) if ct.exam_id else None
        subject_obj = Subject.query.get(exam_obj.subject_id) if exam_obj else None
        # Submissions count from sessions
        submissions = ExamSession.query.filter_by(exam_id=exam_obj.id, status='completed').count() if exam_obj else 0
        test_items.append({
            'exam_id': exam_obj.id if exam_obj else None,
            'title': exam_obj.title if exam_obj else f'Custom Test #{ct.id}',
            'subject_name': subject_obj.name if subject_obj else 'Unknown',
            'created_at': ct.created_at,
            'status': ct.status,
            'submissions': submissions
        })
    return render_template('admin/teacher_tests.html', teacher=teacher, tests=test_items)

@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with comprehensive analytics"""
    try:
        # Get overview statistics
        total_students = User.query.filter_by(role='student').count()
        total_sessions = ExamSession.query.filter_by(status='completed').count()
        total_questions = Question.query.count()
        total_subjects = Subject.query.count()
        
        # Get recent activity (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_sessions = ExamSession.query.filter(
            ExamSession.start_time >= week_ago,
            ExamSession.status == 'completed'
        ).count()
        
        # Calculate average performance
        avg_performance = db.session.query(func.avg(ExamSession.percentage))\
                                   .filter_by(status='completed').scalar() or 0
        
        # Get top performing students (last 30 days)
        month_ago = datetime.utcnow() - timedelta(days=30)
        top_students = db.session.query(
            User.id,
            User.username,
            User.email,
            func.avg(ExamSession.percentage).label('avg_score'),
            func.count(ExamSession.id).label('total_tests')
        ).join(ExamSession).filter(
            ExamSession.start_time >= month_ago,
            ExamSession.status == 'completed'
        ).group_by(User.id).order_by(desc('avg_score')).limit(10).all()
        
        # Get subject-wise performance
        subject_performance = db.session.query(
            Subject.name,
            func.avg(ExamSession.percentage).label('avg_score'),
            func.count(ExamSession.id).label('total_attempts')
        ).select_from(Subject).join(Exam, Subject.id == Exam.subject_id).join(ExamSession, Exam.id == ExamSession.exam_id).filter(
            ExamSession.status == 'completed'
        ).group_by(Subject.id).all()
        
        # Get daily activity for the last 30 days
        daily_activity = []
        for i in range(30):
            date = datetime.utcnow() - timedelta(days=i)
            date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date_start + timedelta(days=1)
            
            sessions_count = ExamSession.query.filter(
                ExamSession.start_time >= date_start,
                ExamSession.start_time < date_end,
                ExamSession.status == 'completed'
            ).count()
            
            daily_activity.append({
                'date': date.strftime('%Y-%m-%d'),
                'sessions': sessions_count
            })
        
        daily_activity.reverse()  # Show oldest to newest
        
        return render_template('admin/dashboard.html',
                             total_students=total_students,
                             total_sessions=total_sessions,
                             total_questions=total_questions,
                             total_subjects=total_subjects,
                             recent_sessions=recent_sessions,
                             avg_performance=round(avg_performance, 1),
                             top_students=top_students,
                             subject_performance=subject_performance,
                             daily_activity=daily_activity)
    
    except Exception as e:
        current_app.logger.error(f"Error in admin dashboard: {str(e)}")
        flash('Error loading dashboard', 'error')
        return redirect(url_for('main.index'))


@bp.route('/theme', methods=['GET'])
@login_required
@admin_required
def theme_settings():
    # Only allow superadmin to change site theme
    if getattr(current_user, 'role', None) != 'superadmin':
        flash('Superadmin access required to change theme', 'error')
        return redirect(url_for('admin.dashboard'))

    current_theme = SiteSetting.get('ui_theme', default='default')
    themes = [
        {'id': 'default', 'name': 'Default (purple)', 'primary': '#667eea'},
        {'id': 'blue', 'name': 'Blue', 'primary': '#0d6efd'},
        {'id': 'green', 'name': 'Green', 'primary': '#198754'},
        {'id': 'dark', 'name': 'Dark', 'primary': '#343a40'},
        {'id': 'sunset', 'name': 'Sunset', 'primary': '#ff7e5f'}
    ]
    site_title = SiteSetting.get('site_title', default='AKSHARASHREE')
    return render_template('admin/theme_settings.html', current_theme=current_theme, themes=themes, site_title=site_title)


@bp.route('/theme', methods=['POST'])
@login_required
@admin_required
def theme_update():
    if getattr(current_user, 'role', None) != 'superadmin':
        return jsonify({'success': False, 'message': 'Superadmin access required'}), 403

    selected = request.form.get('theme')
    site_title = request.form.get('site_title')
    # site_title can be updated even if theme is not changed
    try:
        if site_title is not None:
            SiteSetting.set('site_title', site_title.strip())
        if selected:
            SiteSetting.set('ui_theme', selected)
            flash('Theme and site title updated successfully', 'success')
        else:
            flash('Site title updated successfully', 'success')
        return redirect(url_for('admin.theme_settings'))
    except Exception as e:
        current_app.logger.error(f"Failed to update theme/site title: {e}")
        flash('Failed to update theme or site title', 'error')
        return redirect(url_for('admin.theme_settings'))

@bp.route('/students')
@login_required
@admin_required
def students():
    """Student management and analytics"""
    try:
        # Get all students with their statistics
        students_data = []
        students = User.query.filter_by(role='student').all()
        
        for student in students:
            # Get student's session statistics
            total_sessions = ExamSession.query.filter_by(
                user_id=student.id, status='completed'
            ).count()
            
            avg_score = db.session.query(func.avg(ExamSession.percentage))\
                                 .filter_by(user_id=student.id, status='completed').scalar() or 0
            
            best_score = db.session.query(func.max(ExamSession.percentage))\
                                  .filter_by(user_id=student.id, status='completed').scalar() or 0
            
            # Get recent activity
            week_ago = datetime.utcnow() - timedelta(days=7)
            recent_sessions = ExamSession.query.filter(
                ExamSession.user_id == student.id,
                ExamSession.start_time >= week_ago,
                ExamSession.status == 'completed'
            ).count()
            
            # Calculate rank among all students
            all_avg_scores = db.session.query(
                User.id,
                func.avg(ExamSession.percentage).label('avg_score')
            ).join(ExamSession).filter(
                ExamSession.status == 'completed'
            ).group_by(User.id).all()
            
            sorted_scores = sorted(all_avg_scores, key=lambda x: x.avg_score or 0, reverse=True)
            rank = next((i + 1 for i, s in enumerate(sorted_scores) if s.id == student.id), None)
            
            students_data.append({
                'student': student,
                'total_sessions': total_sessions,
                'avg_score': round(avg_score, 1),
                'best_score': round(best_score, 1),
                'recent_sessions': recent_sessions,
                'rank': rank or 'N/A'
            })
        
        # Sort by average score
        students_data.sort(key=lambda x: x['avg_score'], reverse=True)
        
        return render_template('admin/students.html', students_data=students_data)
    
    except Exception as e:
        current_app.logger.error(f"Error in students page: {str(e)}")
        flash('Error loading students data', 'error')
        return redirect(url_for('admin.dashboard'))

@bp.route('/student/<int:student_id>')
@login_required
@admin_required
def student_detail(student_id):
    """Detailed analytics for a specific student"""
    try:
        student = User.query.filter_by(id=student_id, role='student').first_or_404()
        
        # Get all sessions for this student
        sessions = ExamSession.query.filter_by(
            user_id=student_id, status='completed'
        ).order_by(desc(ExamSession.start_time)).all()
        
        if not sessions:
            flash('No completed sessions found for this student', 'info')
            return redirect(url_for('admin.students'))
        
        # Calculate comprehensive analytics
        total_sessions = len(sessions)
        avg_score = sum(s.percentage for s in sessions if s.percentage) / total_sessions
        best_score = max(s.percentage for s in sessions if s.percentage)
        worst_score = min(s.percentage for s in sessions if s.percentage)
        
        # Subject-wise performance
        subject_stats = {}
        topic_stats = {}
        difficulty_stats = {
            'easy': {'total': 0, 'correct': 0, 'percentage': 0},
            'moderate': {'total': 0, 'correct': 0, 'percentage': 0},
            'difficult': {'total': 0, 'correct': 0, 'percentage': 0}
        }
        
        # Analyze all questions across sessions
        for session in sessions:
            questions_data = session.get_questions_data()
            questions = questions_data.get('questions', [])
            
            for question in questions:
                question_id = question.get('question_id')
                if not question_id:
                    continue
                
                q = Question.query.get(question_id)
                if not q or not q.topic:
                    continue
                
                subject_name = q.topic.subject.name
                topic_name = q.topic.name
                difficulty = q.difficulty_level.lower() if q.difficulty_level else 'moderate'
                is_correct = question.get('is_correct', False)
                
                # Subject stats
                if subject_name not in subject_stats:
                    subject_stats[subject_name] = {'total': 0, 'correct': 0, 'percentage': 0}
                subject_stats[subject_name]['total'] += 1
                if is_correct:
                    subject_stats[subject_name]['correct'] += 1
                
                # Topic stats
                if topic_name not in topic_stats:
                    topic_stats[topic_name] = {
                        'total': 0, 'correct': 0, 'percentage': 0, 'subject': subject_name
                    }
                topic_stats[topic_name]['total'] += 1
                if is_correct:
                    topic_stats[topic_name]['correct'] += 1
                
                # Difficulty stats
                if difficulty in difficulty_stats:
                    difficulty_stats[difficulty]['total'] += 1
                    if is_correct:
                        difficulty_stats[difficulty]['correct'] += 1
        
        # Calculate percentages
        for subject in subject_stats.values():
            subject['percentage'] = (subject['correct'] / subject['total'] * 100) if subject['total'] > 0 else 0
        
        for topic in topic_stats.values():
            topic['percentage'] = (topic['correct'] / topic['total'] * 100) if topic['total'] > 0 else 0
        
        for difficulty in difficulty_stats.values():
            difficulty['percentage'] = (difficulty['correct'] / difficulty['total'] * 100) if difficulty['total'] > 0 else 0
        
        # Performance trend
        performance_trend = []
        for session in reversed(sessions[-20:]):  # Last 20 sessions
            performance_trend.append({
                'date': session.start_time.strftime('%m/%d'),
                'percentage': session.percentage
            })
        
        # Calculate rank and percentile
        all_students = User.query.filter_by(role='student').all()
        student_scores = []
        for s in all_students:
            s_avg = db.session.query(func.avg(ExamSession.percentage))\
                             .filter_by(user_id=s.id, status='completed').scalar()
            if s_avg:
                student_scores.append(s_avg)
        
        if student_scores:
            student_scores.sort(reverse=True)
            rank = student_scores.index(avg_score) + 1 if avg_score in student_scores else None
            percentile = ((len(student_scores) - rank + 1) / len(student_scores) * 100) if rank else 0
        else:
            rank = None
            percentile = 0
        
        return render_template('admin/student_detail.html',
                             student=student,
                             sessions=sessions[:10],  # Recent 10 sessions
                             total_sessions=total_sessions,
                             avg_score=round(avg_score, 1),
                             best_score=round(best_score, 1),
                             worst_score=round(worst_score, 1),
                             subject_stats=subject_stats,
                             topic_stats=topic_stats,
                             difficulty_stats=difficulty_stats,
                             performance_trend=performance_trend,
                             rank=rank,
                             percentile=round(percentile, 1))
    
    except Exception as e:
        current_app.logger.error(f"Error in student detail: {str(e)}")
        flash('Error loading student details', 'error')
        return redirect(url_for('admin.students'))

from sqlalchemy.orm import joinedload

@bp.route('/sessions')
@login_required
@admin_required
def sessions():
    """All exam sessions with filtering and analytics"""
    try:
        # Get filter parameters
        student_id = request.args.get('student_id', type=int)
        subject_id = request.args.get('subject_id', type=int)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Build query with eager loading for exam and subject
        query = ExamSession.query.options(
            joinedload(ExamSession.exam).joinedload(Exam.subject),
            joinedload(ExamSession.user)
        ).filter_by(status='completed')
        
        if student_id:
            query = query.filter_by(user_id=student_id)
        
        if subject_id:
            query = query.join(Exam, ExamSession.exam_id == Exam.id).filter(Exam.subject_id == subject_id)
        
        if date_from:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(ExamSession.start_time >= date_from_obj)
        
        if date_to:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(ExamSession.start_time < date_to_obj)
        
        # Get sessions with user and exam data
        sessions = query.order_by(desc(ExamSession.start_time)).limit(100).all()
        
        # Get filter options
        students = User.query.filter_by(role='student').order_by(User.username).all()
        subjects = Subject.query.order_by(Subject.name).all()
        
        # Calculate session analytics
        session_analytics = []
        for session in sessions:
            # Calculate rank for this session
            same_exam_sessions = ExamSession.query.filter_by(
                exam_id=session.exam_id, status='completed'
            ).all()
            
            if same_exam_sessions:
                scores = [s.percentage for s in same_exam_sessions if s.percentage is not None]
                scores.sort(reverse=True)
                rank = scores.index(session.percentage) + 1 if session.percentage in scores else None
                percentile = ((len(scores) - rank + 1) / len(scores) * 100) if rank else 0
            else:
                rank = None
                percentile = 0
            
            session_analytics.append({
                'session': session,
                'rank': rank,
                'percentile': round(percentile, 1),
                'total_participants': len(same_exam_sessions) if same_exam_sessions else 0
            })
        
        return render_template('admin/sessions.html',
                             session_analytics=session_analytics,
                             students=students,
                             subjects=subjects,
                             filters={
                                 'student_id': student_id,
                                 'subject_id': subject_id,
                                 'date_from': date_from,
                                 'date_to': date_to
                             })
    
    except Exception as e:
        current_app.logger.error(f"Error in sessions page: {str(e)}")
        flash('Error loading sessions', 'error')
        return redirect(url_for('admin.dashboard'))
    
@bp.route('/session/<int:session_id>')
@login_required
@admin_required
def session_detail(session_id):
    """Detailed view of a specific session"""
    try:
        # Get session - allow any status for admin viewing
        session = ExamSession.query.get_or_404(session_id)
        
        # Initialize default values
        detailed_questions = []
        analytics = {
            'total_questions': 0,
            'attempted': 0,
            'skipped': 0,
            'correct': 0,
            'incorrect': 0,
            'accuracy': 0,
            'time_analysis': {
                'total_time': session.duration_seconds or 0,
                'avg_per_question': 0,
                'fastest': 0,
                'slowest': 0
            },
            'difficulty_breakdown': {
                'easy': {'total': 0, 'correct': 0, 'accuracy': 0},
                'moderate': {'total': 0, 'correct': 0, 'accuracy': 0},
                'difficult': {'total': 0, 'correct': 0, 'accuracy': 0}
            }
        }
        comparative_data = {'total_participants': 0}
        
        # Try to get questions data safely
        try:
            questions_data = session.get_questions_data()
            if isinstance(questions_data, dict) and 'questions' in questions_data:
                questions = questions_data['questions']
                
                # Process questions for detailed view using canonical keys
                for q_data in questions:
                    if isinstance(q_data, dict):
                        question_id = q_data.get('question_id')
                        if question_id:
                            question = Question.query.get(question_id)
                            if question:
                                detailed_questions.append({
                                    'question': question,
                                    'user_answer': q_data.get('user_answer', q_data.get('answer', '')),
                                    'correct_answer': q_data.get('correct_answer', question.correct_answer),
                                    'is_correct': q_data.get('is_correct', q_data.get('correct', False)),
                                    'is_attempted': q_data.get('is_attempted', bool(q_data.get('user_answer') or q_data.get('answer'))),
                                    'time_spent': q_data.get('time_spent', 0),
                                    'explanation': q_data.get('explanation', question.explanation)
                                })
                
                # Use shared analytics calculator to ensure consistency with student view
                analytics = calculate_session_analytics(session, questions)
                
        except Exception as e:
            current_app.logger.error(f"Error processing session data: {str(e)}")
            flash('Some session data could not be loaded', 'warning')
        
        # Try to get comparative data
        try:
            comparative_data = get_session_comparative_data(session)
        except Exception as e:
            current_app.logger.error(f"Error getting comparative data: {str(e)}")
        
        return render_template('admin/session_detail.html',
                             session=session,
                             questions=detailed_questions,
                             analytics=analytics,
                             comparative_data=comparative_data)
    
    except Exception as e:
        current_app.logger.error(f"Error in session detail: {str(e)}")
        flash('Error loading session details', 'error')
        return redirect(url_for('admin.sessions'))

@bp.route('/analytics')
@login_required
@admin_required
def analytics():
    """Advanced analytics and reports"""
    try:
        # Overall platform analytics
        total_users = User.query.filter_by(role='student').count()
        total_sessions = ExamSession.query.filter_by(status='completed').count()
        
        # Performance distribution
        score_ranges = {
            '90-100': 0, '80-89': 0, '70-79': 0, '60-69': 0, '50-59': 0, 'Below 50': 0
        }
        
        all_sessions = ExamSession.query.filter_by(status='completed').all()
        for session in all_sessions:
            if session.percentage >= 90:
                score_ranges['90-100'] += 1
            elif session.percentage >= 80:
                score_ranges['80-89'] += 1
            elif session.percentage >= 70:
                score_ranges['70-79'] += 1
            elif session.percentage >= 60:
                score_ranges['60-69'] += 1
            elif session.percentage >= 50:
                score_ranges['50-59'] += 1
            else:
                score_ranges['Below 50'] += 1
        
        # Subject difficulty analysis
        subject_difficulty = {}
        subjects = Subject.query.all()
        
        for subject in subjects:
            # Get all sessions for this subject
            subject_sessions = db.session.query(ExamSession)\
                                        .join(Exam, ExamSession.exam_id == Exam.id)\
                                        .filter(Exam.subject_id == subject.id, ExamSession.status == 'completed')\
                                        .all()
            
            if subject_sessions:
                avg_score = sum(s.percentage for s in subject_sessions if s.percentage) / len(subject_sessions)
                subject_difficulty[subject.name] = {
                    'avg_score': round(avg_score, 1),
                    'total_attempts': len(subject_sessions),
                    'difficulty_level': 'Easy' if avg_score >= 80 else 'Moderate' if avg_score >= 60 else 'Difficult'
                }
        
        # Top performing topics
        topic_performance = {}
        topics = Topic.query.all()
        
        for topic in topics:
            topic_questions = Question.query.filter_by(topic_id=topic.id).all()
            if not topic_questions:
                continue
            
            total_attempts = 0
            correct_attempts = 0
            
            for session in all_sessions:
                questions_data = session.get_questions_data()
                questions = questions_data.get('questions', [])
                
                for q_data in questions:
                    if q_data.get('question_id') in [q.id for q in topic_questions]:
                        total_attempts += 1
                        if q_data.get('is_correct'):
                            correct_attempts += 1
            
            if total_attempts > 0:
                accuracy = (correct_attempts / total_attempts) * 100
                topic_performance[topic.name] = {
                    'accuracy': round(accuracy, 1),
                    'total_attempts': total_attempts,
                    'subject': topic.subject.name
                }
        
        # Sort topic performance
        sorted_topics = sorted(topic_performance.items(), key=lambda x: x[1]['accuracy'], reverse=True)
        
        return render_template('admin/analytics.html',
                             total_users=total_users,
                             total_sessions=total_sessions,
                             score_ranges=score_ranges,
                             subject_difficulty=subject_difficulty,
                             topic_performance=dict(sorted_topics[:20]))  # Top 20 topics
    
    except Exception as e:
        current_app.logger.error(f"Error in analytics: {str(e)}")
        flash('Error loading analytics', 'error')
        return redirect(url_for('admin.dashboard'))

def calculate_session_analytics(session, questions):
    """Calculate detailed analytics for a session"""
    analytics = {
        'total_questions': len(questions),
        'attempted': 0,
        'skipped': 0,
        'correct': 0,
        'incorrect': 0,
        'accuracy': 0,
        'time_analysis': {
            'total_time': session.duration_seconds or 0,
            'avg_per_question': 0,
            'fastest': float('inf'),
            'slowest': 0
        },
        'difficulty_breakdown': {
            'easy': {'total': 0, 'correct': 0, 'accuracy': 0},
            'moderate': {'total': 0, 'correct': 0, 'accuracy': 0},
            'difficult': {'total': 0, 'correct': 0, 'accuracy': 0}
        }
    }
    
    try:
        # Derive total_time with robust fallbacks when duration_seconds is missing
        try:
            if not analytics['time_analysis']['total_time']:
                data = session.get_questions_data() if hasattr(session, 'get_questions_data') else {}
                if isinstance(data, dict):
                    a = data.get('analytics', {})
                    ti = data.get('test_info', {})
                    qt = data.get('question_timings', {})
                    total_time = 0
                    if isinstance(a.get('total_time'), (int, float)):
                        total_time = a.get('total_time')
                    elif isinstance(ti.get('duration_seconds'), (int, float)):
                        total_time = ti.get('duration_seconds')
                    elif isinstance(qt, dict) and qt:
                        try:
                            total_time = sum(v for v in qt.values() if isinstance(v, (int, float)))
                        except Exception:
                            total_time = 0
                    analytics['time_analysis']['total_time'] = int(total_time or 0)
        except Exception:
            pass

        for i, question in enumerate(questions):
            try:
                # Handle both dict and object formats
                if isinstance(question, dict):
                    is_attempted = question.get('is_attempted', False) or bool(question.get('user_answer') or question.get('answer'))
                    is_correct = question.get('is_correct', question.get('correct', False))
                    time_spent = question.get('time_spent', 0)
                    question_id = question.get('question_id')
                else:
                    # Handle object format
                    is_attempted = getattr(question, 'is_attempted', False) or bool(getattr(question, 'user_answer', None))
                    is_correct = getattr(question, 'is_correct', False)
                    time_spent = getattr(question, 'time_spent', 0)
                    question_id = getattr(question, 'question_id', None)
                
                if is_attempted:
                    analytics['attempted'] += 1
                    if is_correct:
                        analytics['correct'] += 1
                    else:
                        analytics['incorrect'] += 1
                else:
                    analytics['skipped'] += 1
                
                # Time analysis
                if time_spent and time_spent > 0:
                    analytics['time_analysis']['fastest'] = min(analytics['time_analysis']['fastest'], time_spent)
                    analytics['time_analysis']['slowest'] = max(analytics['time_analysis']['slowest'], time_spent)
                
                # Difficulty analysis
                if question_id:
                    try:
                        q = Question.query.get(question_id)
                        if q and q.difficulty_level:
                            difficulty = q.difficulty_level.lower()
                            if difficulty in analytics['difficulty_breakdown']:
                                analytics['difficulty_breakdown'][difficulty]['total'] += 1
                                if is_correct:
                                    analytics['difficulty_breakdown'][difficulty]['correct'] += 1
                    except Exception as e:
                        current_app.logger.error(f"Error processing question {question_id}: {str(e)}")
                        continue
                        
            except Exception as e:
                current_app.logger.error(f"Error processing question {i}: {str(e)}")
                continue
        
        # Calculate derived metrics
        if analytics['attempted'] > 0:
            analytics['accuracy'] = (analytics['correct'] / analytics['attempted']) * 100
        
        if analytics['total_questions'] > 0:
            analytics['time_analysis']['avg_per_question'] = analytics['time_analysis']['total_time'] / analytics['total_questions']
        
        if analytics['time_analysis']['fastest'] == float('inf'):
            analytics['time_analysis']['fastest'] = 0
        
        # Calculate difficulty accuracies
        for difficulty in analytics['difficulty_breakdown']:
            total = analytics['difficulty_breakdown'][difficulty]['total']
            correct = analytics['difficulty_breakdown'][difficulty]['correct']
            analytics['difficulty_breakdown'][difficulty]['accuracy'] = (correct / total * 100) if total > 0 else 0
        
    except Exception as e:
        current_app.logger.error(f"Error in calculate_session_analytics: {str(e)}")
    
    return analytics

def get_session_comparative_data(session):
    """Get comparative data for a session"""
    try:
        # Get all sessions for the same exam
        same_exam_sessions = ExamSession.query.filter_by(
            exam_id=session.exam_id, status='completed'
        ).all()
        
        if not same_exam_sessions:
            return {'total_participants': 0}
        
        scores = [s.percentage for s in same_exam_sessions if s.percentage is not None]
        times = [s.duration_seconds for s in same_exam_sessions if s.duration_seconds is not None]
        
        if not scores:
            return {'total_participants': len(same_exam_sessions)}
        
        # Calculate rank and percentile
        scores.sort(reverse=True)
        rank = scores.index(session.percentage) + 1 if session.percentage in scores else None
        percentile = ((len(scores) - rank + 1) / len(scores) * 100) if rank else 0
        
        # Time comparison
        faster_than = 0
        slower_than = 0
        if session.duration_seconds and times:
            faster_than = sum(1 for t in times if t > session.duration_seconds)
            slower_than = sum(1 for t in times if t < session.duration_seconds)
            faster_than_percent = (faster_than / len(times)) * 100
            slower_than_percent = (slower_than / len(times)) * 100
        else:
            faster_than_percent = 0
            slower_than_percent = 0
        
        return {
            'total_participants': len(same_exam_sessions),
            'rank': rank,
            'percentile': round(percentile, 1),
            'avg_score': round(sum(scores) / len(scores), 1),
            'fastest_time': min(times) if times else 0,
            'slowest_time': max(times) if times else 0,
            'faster_than_percent': round(faster_than_percent, 1),
            'slower_than_percent': round(slower_than_percent, 1)
        }
    
    except Exception as e:
        current_app.logger.error(f"Error calculating comparative data: {str(e)}")
        return {'total_participants': 0}


# Student CRUD Operations
@bp.route('/students/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_student():
    """Add a new student"""
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            
            # Validation
            if not username or not email or not password:
                flash('All fields are required', 'error')
                return render_template('admin/add_student.html')
            
            # Check if username or email already exists
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'error')
                return render_template('admin/add_student.html')
            
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'error')
                return render_template('admin/add_student.html')
            
            # Create new student
            student = User(
                username=username,
                email=email,
                role='student',
                is_active=True
            )
            student.set_password(password)
            
            db.session.add(student)
            db.session.commit()
            
            flash(f'Student {username} added successfully', 'success')
            return redirect(url_for('admin.students'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding student: {str(e)}")
            flash('Error adding student', 'error')
    
    return render_template('admin/add_student.html')


@bp.route('/students/edit/<int:student_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(student_id):
    """Edit an existing student"""
    student = User.query.filter_by(id=student_id, role='student').first_or_404()
    
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            is_active = request.form.get('is_active') == 'on'
            
            # Validation
            if not username or not email:
                flash('Username and email are required', 'error')
                return render_template('admin/edit_student.html', student=student)
            
            # Check if username already exists (excluding current student)
            existing_user = User.query.filter(User.username == username, User.id != student_id).first()
            if existing_user:
                flash('Username already exists', 'error')
                return render_template('admin/edit_student.html', student=student)
            
            # Check if email already exists (excluding current student)
            existing_email = User.query.filter(User.email == email, User.id != student_id).first()
            if existing_email:
                flash('Email already exists', 'error')
                return render_template('admin/edit_student.html', student=student)
            
            # Update student
            student.username = username
            student.email = email
            student.is_active = is_active
            
            # Update password if provided
            if password:
                student.set_password(password)
            
            db.session.commit()
            
            flash(f'Student {username} updated successfully', 'success')
            return redirect(url_for('admin.students'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating student: {str(e)}")
            flash('Error updating student', 'error')
    
    # Calculate student statistics for display
    try:
        # Get basic session counts
        completed_sessions = student.exam_sessions.filter_by(status='completed').count()
        in_progress_sessions = student.exam_sessions.filter_by(status='in_progress').count()
        
        # Calculate average score
        sessions_with_scores = [s for s in student.exam_sessions.filter_by(status='completed').all() if s.percentage is not None]
        avg_score = sum(s.percentage for s in sessions_with_scores) / len(sessions_with_scores) if sessions_with_scores else 0
        
        # Get recent activity (last 7 days)
        from datetime import datetime, timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_sessions = student.exam_sessions.filter(
            ExamSession.start_time >= week_ago,
            ExamSession.status == 'completed'
        ).count()
        
        # Package statistics for template
        student_stats = {
            'completed_sessions': completed_sessions,
            'in_progress_sessions': in_progress_sessions,
            'avg_score': round(avg_score, 1),
            'recent_sessions': recent_sessions
        }
        
    except Exception as e:
        current_app.logger.error(f"Error calculating student stats: {str(e)}")
        student_stats = {
            'completed_sessions': 0,
            'in_progress_sessions': 0,
            'avg_score': 0,
            'recent_sessions': 0
        }
    
    return render_template('admin/edit_student.html', student=student, student_stats=student_stats)


@bp.route('/students/delete/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def delete_student(student_id):
    """Delete a student"""
    try:
        student = User.query.filter_by(id=student_id, role='student').first_or_404()
        
        # Check if student has exam sessions
        session_count = ExamSession.query.filter_by(user_id=student_id).count()
        
        if session_count > 0:
            # Don't actually delete, just deactivate
            student.is_active = False
            db.session.commit()
            flash(f'Student {student.username} deactivated (has {session_count} exam sessions)', 'warning')
        else:
            # Safe to delete
            username = student.username
            db.session.delete(student)
            db.session.commit()
            flash(f'Student {username} deleted successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting student: {str(e)}")
        flash('Error deleting student', 'error')
    
    return redirect(url_for('admin.students'))


@bp.route('/students/toggle-status/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def toggle_student_status(student_id):
    """Toggle student active status"""
    try:
        student = User.query.filter_by(id=student_id, role='student').first_or_404()
        
        student.is_active = not student.is_active
        db.session.commit()
        
        status = 'activated' if student.is_active else 'deactivated'
        flash(f'Student {student.username} {status} successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling student status: {str(e)}")
        flash('Error updating student status', 'error')
    
    return redirect(url_for('admin.students'))

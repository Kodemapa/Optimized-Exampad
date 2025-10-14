"""
API Blueprint - RESTful API endpoints (database-backed)
"""

import random
import re
import json
import os
from flask import Blueprint, jsonify, request, send_file
from html import unescape
from datetime import datetime
from app.models import db, Subject, Topic, Question, StudentRegistration

bp = Blueprint('api', __name__)

@bp.route('/register-student', methods=['POST'])
def register_student():
    try:
        data = request.get_json()

        # Extract data from the request
        application_no = data.get('application_no')
        exam_date = datetime.strptime(data.get('exam_date'), '%d-%m-%Y').date() if data.get('exam_date') else None
        student_name = data.get('student_name')
        father_name = data.get('father_name')
        student_class = data.get('class')
        school = data.get('school')
        board = data.get('board')
        contact_1 = data.get('contact_1')
        contact_2 = data.get('contact_2')
        email = data.get('email')
        address = data.get('address')
        reference_1_name = data.get('reference_1_name')
        reference_1_contact = data.get('reference_1_contact')
        reference_2_name = data.get('reference_2_name')
        reference_2_contact = data.get('reference_2_contact')

        # Validate required fields
        required_fields = ['application_no', 'student_name', 'contact_1']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'status': 'error',
                    'message': f'{field.replace("_", " ").title()} is required'
                }), 400

        # Create new student registration
        registration = StudentRegistration(
            application_no=application_no,
            exam_date=exam_date,
            student_name=student_name,
            father_name=father_name,
            class_name=student_class,
            school=school,
            board=board,
            contact_1=contact_1,
            contact_2=contact_2,
            email=email,
            address=address,
            reference_1_name=reference_1_name,
            reference_1_contact=reference_1_contact,
            reference_2_name=reference_2_name,
            reference_2_contact=reference_2_contact
        )

        # Add to database
        db.session.add(registration)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Student registration completed successfully',
            'data': {
                'application_no': application_no
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

def convert_options_for_frontend(question):
    """
    Convert options from A,B,C,D dict format to array for frontend compatibility.
    Also converts correct_answer from letter to index.
    Returns tuple: (options_array, correct_answer_index)
    """
    options_dict = question.get_options()
    options_array = []
    correct_answer_letter = question.correct_answer
    
    if isinstance(options_dict, dict):
        # Convert from {"A": "option1", "B": "option2", ...} to ["option1", "option2", ...]
        for letter in ['A', 'B', 'C', 'D']:
            if letter in options_dict:
                options_array.append(options_dict[letter])
            else:
                options_array.append("")  # Empty if missing option
        
        # Convert correct answer from letter to index (A=0, B=1, C=2, D=3)
        if correct_answer_letter in ['A', 'B', 'C', 'D']:
            correct_answer_index = ord(correct_answer_letter) - ord('A')
        else:
            correct_answer_index = 0  # Default to A if invalid
    else:
        # Fallback for old format (if any still exist)
        options_array = options_dict if isinstance(options_dict, list) else []
        try:
            correct_answer_index = int(correct_answer_letter) - 1 if correct_answer_letter.isdigit() else 0
        except:
            correct_answer_index = 0
    
    return options_array, correct_answer_index

# API Routes (database-backed)
@bp.route('/classes', methods=['GET'])
def get_classes():
    """Return list of available classes."""
    return jsonify({'classes': ['XI', 'XII']})

@bp.route('/subjects/<class_selection>', methods=['GET'])
def get_subjects(class_selection):
    """Return list of subjects for the selected class."""
    if class_selection not in ['XI', 'XII']:
        return jsonify({'error': f'Class {class_selection} not found'}), 404
    
    # Get subjects for the specified class
    subjects = Subject.query.filter_by(class_level=class_selection).all()
    
    if not subjects:
        return jsonify({'error': f'No subjects found for class {class_selection}'}), 404
    
    subjects_data = [{'id': subject.id, 'name': subject.name} for subject in subjects]
    return jsonify({'subjects': subjects_data})

@bp.route('/topics/<class_selection>/<int:subject_id>', methods=['GET'])
def get_topics(class_selection, subject_id):
    """Return topics for a subject."""
    if class_selection not in ['XI', 'XII']:
        return jsonify({'error': f'Class {class_selection} not found'}), 404
    
    # Verify subject exists and belongs to the class
    subject = Subject.query.filter_by(id=subject_id, class_level=class_selection).first()
    if not subject:
        return jsonify({'error': f'Subject ID {subject_id} not found for class {class_selection}'}), 404
    
    # Get topics for this subject
    topics = Topic.query.filter_by(subject_id=subject_id).all()
    
    topics_data = []
    for topic in topics:
        # Count questions for this topic
        question_count = Question.query.filter_by(topic_id=topic.id).count()
        
        topics_data.append({
            'id': topic.id,
            'name': topic.name,
            'description': topic.description,
            'question_count': question_count
        })
    
    return jsonify({
        'subject': {'id': subject.id, 'name': subject.name},
        'topics': topics_data
    })

@bp.route('/questions/sample', methods=['GET'])
def get_sample_questions():
    """Get sample questions with optional filtering."""
    try:
        # Get parameters
        topic_id = request.args.get('topic_id', type=int)
        difficulty = request.args.get('difficulty')
        limit = request.args.get('limit', default=10, type=int)
        
        # Start with base query
        query = Question.query
        
        # Apply filters
        if topic_id:
            query = query.filter_by(topic_id=topic_id)
        if difficulty:
            # Filter by question difficulty level
            query = query.filter(Question.difficulty_level == difficulty)
        
        # Get questions
        questions = query.limit(limit).all()
        
        if not questions:
            return jsonify({'error': 'No questions found with the specified criteria'}), 404
        
        # Format questions for response
        questions_data = []
        for q in questions:
            topic = Topic.query.get(q.topic_id)
            subject = Subject.query.get(topic.subject_id) if topic else None
            
            # Convert options for frontend compatibility
            options_array, correct_answer_index = convert_options_for_frontend(q)
            
            question_data = {
                'id': q.id,
                'qid': q.qid,
                'question': q.question_text,
                'options': options_array,
                'answer': correct_answer_index,
                'explanation': q.explanation,
                'difficulty_level': q.difficulty_level,
                'max_marks': q.max_marks,
                'topic': {
                    'id': topic.id,
                    'name': topic.name,
                    'description': topic.description
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
            'total': len(questions_data),
            'filters': {
                'topic_id': topic_id,
                'difficulty': difficulty,
                'limit': limit
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/questions/random', methods=['POST'])
def get_random_questions():
    """
    Get random sample questions from a specific topic.
    Request JSON:
    {
        "topic_id": 1,
        "count": 10,
        "difficulty": "Easy" (optional)
    }
    """
    try:
        data = request.get_json()
        topic_id = data.get("topic_id")
        count = int(data.get("count", 10))
        difficulty = data.get("difficulty")

        if not topic_id or count <= 0:
            return jsonify({'error': 'Missing or invalid fields: topic_id, count'}), 400

        # Verify topic exists
        topic = Topic.query.get(topic_id)
        if not topic:
            return jsonify({'error': f'Topic ID {topic_id} not found'}), 404

        # Build query
        query = Question.query.filter_by(topic_id=topic_id)
        if difficulty:
            query = query.filter(Question.difficulty_level == difficulty)

        # Get all questions for this topic
        all_questions = query.all()

        if not all_questions:
            return jsonify({'error': 'No questions found for the specified criteria'}), 404

        if count > len(all_questions):
            return jsonify({
                'error': f'Only {len(all_questions)} questions available, but {count} requested'
            }), 400

        # Get random sample
        sample_questions = random.sample(all_questions, count)

        # Format questions for response
        questions_data = []
        for q in sample_questions:
            subject = Subject.query.get(topic.subject_id)
            
            # Convert options for frontend compatibility
            options_array, correct_answer_index = convert_options_for_frontend(q)
            
            question_data = {
                'id': q.id,
                'qid': q.qid,
                'question': q.question_text,
                'options': options_array,
                'answer': correct_answer_index,
                'explanation': q.explanation,
                'difficulty_level': q.difficulty_level,
                'max_marks': q.max_marks,
                'topic': {
                    'id': topic.id,
                    'name': topic.name,
                    'description': topic.description
                },
                'subject': {
                    'id': subject.id,
                    'name': subject.name,
                    'class_level': subject.class_level
                } if subject else None
            }
            questions_data.append(question_data)

        return jsonify({
            'topic_id': topic_id,
            'topic_name': topic.name,
            'total_questions_available': len(all_questions),
            'sample_size': count,
            'difficulty_filter': difficulty,
            'questions': questions_data
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/questions/evaluate', methods=['POST'])
def evaluate_answers():
    """
    Evaluate submitted answers and return results.
    Request JSON:
    {
        "submissions": [
            {
                "question_id": 1,
                "submitted_answer": "A",
                "time_taken": 30
            },
            {
                "question_id": 2,
                "submitted_answer": "B",
                "time_taken": 45
            }
        ]
    }
    """
    try:
        data = request.get_json()
        submissions = data.get("submissions", [])
        
        if not submissions:
            return jsonify({'error': 'No submissions provided'}), 400
        
        results = []
        total_score = 0
        total_possible = 0
        total_time_taken = 0
        correct_count = 0
        incorrect_count = 0
        
        for submission in submissions:
            question_id = submission.get("question_id")
            submitted_answer = submission.get("submitted_answer", "").strip()
            time_taken = submission.get("time_taken", 0)
            
            if not question_id:
                continue
                
            # Get the question from database
            question = Question.query.get(question_id)
            if not question:
                results.append({
                    'question_id': question_id,
                    'error': 'Question not found',
                    'is_correct': False,
                    'score': 0,
                    'max_marks': 0
                })
                continue
            
            # Get correct answer
            correct_answer = question.correct_answer
            max_marks = question.max_marks or 1
            
            # Evaluate the answer
            is_correct = False
            score = 0
            
            if submitted_answer and correct_answer:
                # Handle different answer formats (A, B, C, D or 0, 1, 2, 3)
                submitted_normalized = normalize_answer(submitted_answer)
                correct_normalized = normalize_answer(correct_answer)
                
                is_correct = submitted_normalized == correct_normalized
                score = max_marks if is_correct else 0
            
            # Update counters
            total_score += score
            total_possible += max_marks
            total_time_taken += time_taken
            
            if is_correct:
                correct_count += 1
            else:
                incorrect_count += 1
            
            # Get topic and subject info
            topic = Topic.query.get(question.topic_id)
            subject = Subject.query.get(topic.subject_id) if topic else None
            
            # Convert options for frontend compatibility
            options_array, correct_answer_index = convert_options_for_frontend(question)
            
            result_item = {
                'question_id': question_id,
                'qid': question.qid,
                'submitted_answer': submitted_answer,
                'correct_answer': correct_answer_index,
                'is_correct': is_correct,
                'score': score,
                'max_marks': max_marks,
                'time_taken': time_taken,
                'difficulty_level': question.difficulty_level,
                'question_text': question.question_text,
                'options': options_array,
                'explanation': question.explanation,
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
            
            results.append(result_item)
        
        # Calculate statistics
        total_questions = len(submissions)
        percentage = (total_score / total_possible * 100) if total_possible > 0 else 0
        accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
        average_time_per_question = total_time_taken / total_questions if total_questions > 0 else 0
        
        # Determine grade/performance level
        if percentage >= 90:
            grade = 'A+'
            performance = 'Excellent'
        elif percentage >= 80:
            grade = 'A'
            performance = 'Very Good'
        elif percentage >= 70:
            grade = 'B+'
            performance = 'Good'
        elif percentage >= 60:
            grade = 'B'
            performance = 'Above Average'
        elif percentage >= 50:
            grade = 'C'
            performance = 'Average'
        elif percentage >= 40:
            grade = 'D'
            performance = 'Below Average'
        else:
            grade = 'F'
            performance = 'Poor'
        
        return jsonify({
            'evaluation_summary': {
                'total_questions': total_questions,
                'correct_answers': correct_count,
                'incorrect_answers': incorrect_count,
                'total_score': total_score,
                'total_possible': total_possible,
                'percentage': round(percentage, 2),
                'accuracy': round(accuracy, 2),
                'grade': grade,
                'performance_level': performance,
                'total_time_taken': total_time_taken,
                'average_time_per_question': round(average_time_per_question, 2)
            },
            'detailed_results': results,
            'breakdown_by_difficulty': get_difficulty_breakdown(results),
            'breakdown_by_subject': get_subject_breakdown(results)
        })
        
    except Exception as e:
        return jsonify({'error': f'Evaluation failed: {str(e)}'}), 500

def normalize_answer(answer):
    """Normalize answer format for comparison."""
    if not answer:
        return ""
    
    answer_str = str(answer).strip().upper()
    
    # Handle different formats: A, B, C, D or 0, 1, 2, 3
    if answer_str in ['0', 'A']:
        return 'A'
    elif answer_str in ['1', 'B']:
        return 'B'
    elif answer_str in ['2', 'C']:
        return 'C'
    elif answer_str in ['3', 'D']:
        return 'D'
    
    return answer_str

def get_difficulty_breakdown(results):
    """Get performance breakdown by difficulty level."""
    breakdown = {}
    
    for result in results:
        difficulty = result.get('difficulty_level', 'unknown')
        if difficulty not in breakdown:
            breakdown[difficulty] = {
                'total': 0,
                'correct': 0,
                'total_score': 0,
                'total_possible': 0
            }
        
        breakdown[difficulty]['total'] += 1
        if result['is_correct']:
            breakdown[difficulty]['correct'] += 1
        breakdown[difficulty]['total_score'] += result['score']
        breakdown[difficulty]['total_possible'] += result['max_marks']
    
    # Calculate percentages
    for difficulty in breakdown:
        stats = breakdown[difficulty]
        if stats['total'] > 0:
            stats['accuracy'] = round(stats['correct'] / stats['total'] * 100, 2)
        if stats['total_possible'] > 0:
            stats['percentage'] = round(stats['total_score'] / stats['total_possible'] * 100, 2)
    
    return breakdown

def get_subject_breakdown(results):
    """Get performance breakdown by subject."""
    breakdown = {}
    
    for result in results:
        subject_info = result.get('subject')
        if not subject_info:
            continue
            
        subject_name = subject_info['name']
        if subject_name not in breakdown:
            breakdown[subject_name] = {
                'total': 0,
                'correct': 0,
                'total_score': 0,
                'total_possible': 0
            }
        
        breakdown[subject_name]['total'] += 1
        if result['is_correct']:
            breakdown[subject_name]['correct'] += 1
        breakdown[subject_name]['total_score'] += result['score']
        breakdown[subject_name]['total_possible'] += result['max_marks']
    
    # Calculate percentages
    for subject in breakdown:
        stats = breakdown[subject]
        if stats['total'] > 0:
            stats['accuracy'] = round(stats['correct'] / stats['total'] * 100, 2)
        if stats['total_possible'] > 0:
            stats['percentage'] = round(stats['total_score'] / stats['total_possible'] * 100, 2)
    
    return breakdown

# Additional API endpoints for database statistics
@bp.route('/stats', methods=['GET'])
def get_stats():
    """Get database statistics."""
    try:
        stats = {
            'subjects': Subject.query.count(),
            'topics': Topic.query.count(),
            'questions': Question.query.count(),
            'subjects_by_class': {
                'XI': Subject.query.filter_by(class_level='XI').count(),
                'XII': Subject.query.filter_by(class_level='XII').count()
            },
            'questions_by_difficulty': {}
        }
        
        # Count questions by difficulty level
        for difficulty in ['easy', 'moderate', 'difficult']:
            count = Question.query.filter(Question.difficulty_level == difficulty).count()
            stats['questions_by_difficulty'][difficulty] = count
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/questions/practice', methods=['POST'])
def get_practice_questions():
    """API endpoint to get random questions for practice/test"""
    try:
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
        
        total = query.count()
        if total == 0:
            return jsonify({'error': 'No questions found'}), 404
        
        filtered_questions = []
        
        # Since some questions will be skipped, we may need to fetch more than count to get enough valid ones
        # We'll fetch in chunks until we have enough or run out of questions
        
        chunk_size = max(count, 50)  # Fetch in chunks of at least count or 50
        offset = 0
        
        while len(filtered_questions) < count and offset < total:
            questions_chunk = query.offset(offset).limit(chunk_size).all()
            offset += chunk_size
            
            for q in questions_chunk:
                options = q.get_options()
                explanation = q.explanation
                
                if options and explanation:
                    filtered_questions.append(q)
                    if len(filtered_questions) == count:
                        break
        
        if not filtered_questions:
            return jsonify({'error': 'No questions with options and explanation found'}), 404
        
        questions_data = []
        for q in filtered_questions:
            topic = Topic.query.get(q.topic_id)
            subject = Subject.query.get(topic.subject_id) if topic else None
            
            # Convert options for frontend compatibility
            options_array, correct_answer_index = convert_options_for_frontend(q)
            
            question_data = {
                'id': q.id,
                'qid': q.qid,
                'question': q.question_text,
                'options': options_array,
                'correct_answer': correct_answer_index,
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
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/submit-practice', methods=['POST'])
def submit_practice_test():
    """API endpoint to submit practice test answers and get results"""
    try:
        data = request.get_json()
        answers = data.get('answers', [])
        test_info = data.get('test_info', {})
        
        # Calculate score
        total_questions = len(answers)
        correct_answers = 0
        detailed_results = []
        
        for answer_data in answers:
            question_id = answer_data.get('question_id')
            user_answer = answer_data.get('answer')
            
            question = Question.query.get(question_id)
            if question:
                # Convert options for frontend compatibility
                options_array, correct_answer_index = convert_options_for_frontend(question)
                
                is_correct = question.correct_answer == user_answer
                if is_correct:
                    correct_answers += 1
                
                detailed_results.append({
                    'question_id': question_id,
                    'question': question.question_text,
                    'options': options_array,
                    'user_answer': user_answer,
                    'correct_answer': correct_answer_index,
                    'is_correct': is_correct,
                    'explanation': question.explanation
                })
        
        # Calculate percentage
        percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        return jsonify({
            'score': correct_answers,
            'total': total_questions,
            'percentage': round(percentage, 1),
            'results': detailed_results
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/students', methods=['GET'])
def get_students():
    """Return list of all students for superadmin access with pagination and search."""
    from flask_login import current_user
    from app.models import User, StudentClass
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Get pagination and search parameters
        page = request.args.get('page', 1, type=int)
        per_page = 20  # Fixed to 20 users per page
        search = request.args.get('search', '').strip()
        class_filter = request.args.get('class', '').strip()
        status_filter = request.args.get('status', '').strip()
        
        # Get paginated students with their class information
        students_query = db.session.query(User, StudentClass).outerjoin(
            StudentClass, User.id == StudentClass.user_id
        ).filter(User.role == 'student')
        
        # Apply search filter
        if search:
            students_query = students_query.filter(
                (User.username.ilike(f'%{search}%')) |
                (User.email.ilike(f'%{search}%'))
            )
        
        # Apply class filter
        if class_filter:
            students_query = students_query.filter(StudentClass.class_level == class_filter)
        
        # Apply status filter
        if status_filter:
            if status_filter.lower() == 'active':
                students_query = students_query.filter(User.is_active == True)
            elif status_filter.lower() == 'inactive':
                students_query = students_query.filter(User.is_active == False)
        
        # Get total count
        total_students = students_query.count()
        
        # Apply pagination
        students = students_query.offset((page - 1) * per_page).limit(per_page).all()
        
        students_data = []
        for user, student_class in students:
            student_info = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'is_active': user.is_active,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'class_level': student_class.class_level if student_class else None
            }
            students_data.append(student_info)
        
        # Calculate pagination info
        total_pages = (total_students + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1
        
        return jsonify({
            'students': students_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_students,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev
            },
            'filters': {
                'search': search,
                'class': class_filter,
                'status': status_filter
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@bp.route('/students/search-suggestions', methods=['GET'])
def get_student_search_suggestions():
    """Return search suggestions for students."""
    from flask_login import current_user
    from app.models import User
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        query = request.args.get('q', '').strip()
        if not query or len(query) < 2:
            return jsonify({'suggestions': []})
        
        # Search for students matching the query
        students = User.query.filter(
            User.role == 'student',
            (User.username.ilike(f'%{query}%')) |
            (User.email.ilike(f'%{query}%'))
        ).limit(10).all()
        
        suggestions = []
        for student in students:
            suggestions.append({
                'id': student.id,
                'username': student.username,
                'email': student.email,
                'display': f"{student.username} ({student.email})"
            })
        
        return jsonify({'suggestions': suggestions})
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@bp.route('/student/<int:student_id>/access-settings', methods=['GET'])
def get_student_access_settings(student_id):
    """Get access settings for a specific student."""
    from flask_login import current_user
    from app.models import User, StudentAccessSettings
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Verify student exists
        student = User.query.filter_by(id=student_id, role='student').first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get or create access settings for the student
        access_settings = StudentAccessSettings.query.filter_by(user_id=student_id).first()
        
        if not access_settings:
            # Create default settings (all enabled)
            access_settings = StudentAccessSettings(
                user_id=student_id,
                materials_access=True,
                start_exam_access=True,
                view_results_access=True,
                browse_class_access=True
            )
            db.session.add(access_settings)
            db.session.commit()
        
        return jsonify({
            'materials_access': access_settings.materials_access,
            'start_exam_access': access_settings.start_exam_access,
            'view_results_access': access_settings.view_results_access,
            'browse_class_access': access_settings.browse_class_access
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/student/<int:student_id>/access-settings', methods=['PUT'])
def update_student_access_settings(student_id):
    """Update access settings for a specific student."""
    from flask_login import current_user
    from app.models import User, StudentAccessSettings
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Verify student exists
        student = User.query.filter_by(id=student_id, role='student').first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get or create access settings
        access_settings = StudentAccessSettings.query.filter_by(user_id=student_id).first()
        
        if not access_settings:
            access_settings = StudentAccessSettings(user_id=student_id)
            db.session.add(access_settings)
        
        # Update settings
        access_settings.materials_access = data.get('materials_access', True)
        access_settings.start_exam_access = data.get('start_exam_access', True)
        access_settings.view_results_access = data.get('view_results_access', True)
        access_settings.browse_class_access = data.get('browse_class_access', True)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Access settings updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

# Teacher Management API Endpoints
@bp.route('/teachers', methods=['GET'])
def get_teachers():
    """Get all teachers with basic stats and pagination."""
    from flask_login import current_user
    from app.models import User, CustomTest
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 20  # Fixed to 20 users per page
        
        # Get paginated teachers
        teachers_query = User.query.filter_by(role='teacher')
        
        # Get total count
        total_teachers = teachers_query.count()
        
        # Apply pagination
        teachers = teachers_query.offset((page - 1) * per_page).limit(per_page).all()
        
        teacher_data = []
        for teacher in teachers:
            # Count tests created by this teacher
            tests_created = CustomTest.query.filter_by(created_by_user_id=teacher.id).count()
            active_tests = CustomTest.query.filter_by(created_by_user_id=teacher.id, status='active').count()
            
            teacher_data.append({
                'id': teacher.id,
                'username': teacher.username,
                'email': teacher.email,
                'is_active': teacher.is_active,
                'created_at': teacher.created_at.isoformat() if teacher.created_at else None,
                'tests_created': tests_created,
                'active_tests': active_tests
            })
        
        # Calculate pagination info
        total_pages = (total_teachers + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1
        
        return jsonify({
            'teachers': teacher_data,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_teachers,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/teacher/<int:teacher_id>/access-settings', methods=['GET'])
def get_teacher_access_settings(teacher_id):
    """Get access settings for a specific teacher."""
    from flask_login import current_user
    from app.models import User, TeacherAccessSettings
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Verify teacher exists
        teacher = User.query.filter_by(id=teacher_id, role='teacher').first()
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Get or create access settings for the teacher
        access_settings = TeacherAccessSettings.query.filter_by(user_id=teacher_id).first()
        
        if not access_settings:
            # Create default settings (all enabled)
            access_settings = TeacherAccessSettings(
                user_id=teacher_id,
                create_test_access=True,
                manage_tests_access=True,
                view_submissions_access=True,
                analytics_access=True
            )
            db.session.add(access_settings)
            db.session.commit()
        
        return jsonify({
            'create_test_access': access_settings.create_test_access,
            'manage_tests_access': access_settings.manage_tests_access,
            'view_submissions_access': access_settings.view_submissions_access,
            'analytics_access': access_settings.analytics_access
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@bp.route('/teacher/<int:teacher_id>/access-settings', methods=['PUT'])
def update_teacher_access_settings(teacher_id):
    """Update access settings for a specific teacher."""
    from flask_login import current_user
    from app.models import User, TeacherAccessSettings
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Verify teacher exists
        teacher = User.query.filter_by(id=teacher_id, role='teacher').first()
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get or create access settings
        access_settings = TeacherAccessSettings.query.filter_by(user_id=teacher_id).first()
        
        if not access_settings:
            access_settings = TeacherAccessSettings(user_id=teacher_id)
            db.session.add(access_settings)
        
        # Update settings
        access_settings.create_test_access = data.get('create_test_access', True)
        access_settings.manage_tests_access = data.get('manage_tests_access', True)
        access_settings.view_submissions_access = data.get('view_submissions_access', True)
        access_settings.analytics_access = data.get('analytics_access', True)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Access settings updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@bp.route('/student/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    """Delete a student and all associated data."""
    from flask_login import current_user
    from app.models import User, StudentClass, StudentAccessSettings
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Verify student exists
        student = User.query.filter_by(id=student_id, role='student').first()
        if not student:
            return jsonify({'error': 'Student not found'}), 404
        
        # Delete associated student class record
        student_class = StudentClass.query.filter_by(user_id=student_id).first()
        if student_class:
            db.session.delete(student_class)
        
        # Delete associated access settings
        access_settings = StudentAccessSettings.query.filter_by(user_id=student_id).first()
        if access_settings:
            db.session.delete(access_settings)
        
        # Store username for response
        username = student.username
        
        # Delete the student user account
        db.session.delete(student)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Student "{username}" has been successfully deleted'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'An error occurred while deleting student: {str(e)}'}), 500


@bp.route('/teacher/<int:teacher_id>', methods=['DELETE'])
def delete_teacher(teacher_id):
    """Delete a teacher and all associated data."""
    from flask_login import current_user
    from app.models import User, TeacherAccessSettings, CustomTest, Exam
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Verify teacher exists
        teacher = User.query.filter_by(id=teacher_id, role='teacher').first()
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404
        
        # Store username for response before deletion
        username = teacher.username
        
        # Step 1: Delete associated access settings
        access_settings = TeacherAccessSettings.query.filter_by(user_id=teacher_id).first()
        if access_settings:
            db.session.delete(access_settings)
        
        # Step 2: Delete ALL exams created by this teacher (comprehensive approach)
        from app.models import ExamSession
        all_teacher_exams = Exam.query.filter_by(created_by=teacher_id).all()
        deleted_sessions_count = 0
        deleted_exams_count = 0
        
        # Delete exam sessions first, then exams
        for exam in all_teacher_exams:
            # First delete all exam sessions that reference this exam
            exam_sessions = ExamSession.query.filter_by(exam_id=exam.id).all()
            for session in exam_sessions:
                db.session.delete(session)
                deleted_sessions_count += 1
            
            # Then delete the exam
            db.session.delete(exam)
            deleted_exams_count += 1
        
        # Step 3: Delete associated custom tests created by this teacher
        custom_tests = CustomTest.query.filter_by(created_by_user_id=teacher_id).all()
        for custom_test in custom_tests:
            db.session.delete(custom_test)
        
        # Step 4: Delete the teacher user account
        db.session.delete(teacher)
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Teacher "{username}" and all associated data have been successfully deleted',
            'details': {
                'teacher_access_settings_deleted': 1 if access_settings else 0,
                'exams_deleted': deleted_exams_count,
                'exam_sessions_deleted': deleted_sessions_count,
                'custom_tests_deleted': len(custom_tests)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'An error occurred while deleting teacher: {str(e)}'}), 500


@bp.route('/students/statistics', methods=['GET'])
def get_students_statistics():
    """Get detailed statistics for students."""
    from flask_login import current_user
    from app.models import User, StudentClass
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Get all students
        all_students = User.query.filter_by(role='student').all()
        
        # Calculate statistics
        total_students = len(all_students)
        active_students = len([s for s in all_students if s.is_active])
        
        # Get class information
        class_xi_students = db.session.query(User).join(
            StudentClass, User.id == StudentClass.user_id
        ).filter(
            User.role == 'student',
            StudentClass.class_level == 'XI'
        ).count()
        
        class_xii_students = db.session.query(User).join(
            StudentClass, User.id == StudentClass.user_id
        ).filter(
            User.role == 'student',
            StudentClass.class_level == 'XII'
        ).count()
        
        return jsonify({
            'success': True,
            'total_students': total_students,
            'active_students': active_students,
            'class_xi_students': class_xi_students,
            'class_xii_students': class_xii_students
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@bp.route('/teachers/statistics', methods=['GET'])
def get_teachers_statistics():
    """Get detailed statistics for teachers."""
    from flask_login import current_user
    from app.models import User, CustomTest
    
    # Check if current user is superadmin
    if not current_user.is_authenticated or current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied. Superadmin role required.'}), 403
    
    try:
        # Get all teachers
        all_teachers = User.query.filter_by(role='teacher').all()
        
        # Calculate statistics
        total_teachers = len(all_teachers)
        active_teachers = len([t for t in all_teachers if t.is_active])
        
        # Get test statistics
        tests_created = CustomTest.query.count()
        active_tests = CustomTest.query.filter_by(status='active').count()
        
        return jsonify({
            'success': True,
            'total_teachers': total_teachers,
            'active_teachers': active_teachers,
            'tests_created': tests_created,
            'active_tests': active_tests
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

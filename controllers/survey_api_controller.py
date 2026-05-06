# -*- coding: utf-8 -*-

"""
Survey API Controller
Public API endpoint to submit survey responses

Base URL: /api/survey/
Authentication: Public (no auth required)
"""

from odoo import http
from odoo.http import request, Response
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = {
    'https://intellisyncdata.com',
    'https://www.intellisyncdata.com',
    'https://e-hub.vn',
    'https://www.e-hub.vn',
}


def json_response(data, status=200):
    """Helper to create JSON response with CORS headers"""
    response = Response(
        json.dumps(data, default=str, ensure_ascii=False),
        status=status,
        mimetype='application/json'
    )
    # Add CORS headers to allow cross-origin requests
    origin = request.httprequest.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Vary'] = 'Origin'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    requested_headers = request.httprequest.headers.get('Access-Control-Request-Headers')
    response.headers['Access-Control-Allow-Headers'] = requested_headers or (
        'Content-Type, Authorization, Accept, Origin, X-Requested-With'
    )
    response.headers['Access-Control-Max-Age'] = '86400'  # 24 hours
    return response


def validate_answer_value(question, answer_value):
    """
    Validate answer value against question type
    Returns (is_valid, error_message)
    """
    question_type = question.question_type

    # Allow empty/null values
    if answer_value is None or (isinstance(answer_value, str) and not answer_value.strip()):
        return True, None

    # Validate based on question type
    if question_type == 'numerical_box':
        try:
            float(answer_value)
            return True, None
        except (ValueError, TypeError):
            return False, f"Question '{question.title}' expects a number, got: {answer_value}"

    elif question_type == 'date':
        # Accept ISO format date: YYYY-MM-DD
        if isinstance(answer_value, str):
            try:
                datetime.strptime(answer_value, '%Y-%m-%d')
                return True, None
            except ValueError:
                return False, f"Question '{question.title}' expects date format YYYY-MM-DD, got: {answer_value}"
        return False, f"Question '{question.title}' expects a date string, got: {type(answer_value).__name__}"

    elif question_type == 'datetime':
        # Accept ISO format datetime: YYYY-MM-DD HH:MM:SS or ISO 8601
        if isinstance(answer_value, str):
            try:
                # Try multiple datetime formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                    try:
                        datetime.strptime(answer_value, fmt)
                        return True, None
                    except ValueError:
                        continue
                return False, f"Question '{question.title}' expects datetime format YYYY-MM-DD HH:MM:SS, got: {answer_value}"
            except Exception:
                return False, f"Question '{question.title}' expects a datetime string, got: {answer_value}"
        return False, f"Question '{question.title}' expects a datetime string, got: {type(answer_value).__name__}"

    elif question_type == 'multiple_choice':
        # Must be a list for multiple choice
        if not isinstance(answer_value, list):
            return False, f"Question '{question.title}' expects a list of values, got: {type(answer_value).__name__}"
        return True, None

    # For text_box, char_box, simple_choice - accept any string
    return True, None


class SurveyAPIController(http.Controller):
    """
    RESTful API Controller for Survey submission
    """

    @http.route('/api/survey/<int:survey_id>/submit', type='http', auth='public', methods=['POST'], csrf=False)
    def submit_survey(self, survey_id, **kwargs):
        """
        Submit survey response via API
        POST /api/survey/<survey_id>/submit

        Body: {
            "survey_id": 1,
            "answers": {
                "question_1": "Answer 1",
                "question_2": ["Option 1", "Option 2"],
                ...
            },
            "email": "test@example.com",  // Optional
            "partner_id": 123  // Optional
        }

        Returns: {
            "success": true,
            "user_input_id": 42,
            "message": "Survey submitted successfully"
        }
        """
        if request.httprequest.method == 'OPTIONS':
            return json_response({'status': 'ok'}, status=200)
        try:
            # Parse request body
            data = json.loads(request.httprequest.data.decode('utf-8'))
            answers = data.get('answers', {})

            if not answers:
                return json_response({'error': 'Missing answers'}, status=400)

            # Find survey
            survey = request.env['survey.survey'].sudo().browse(survey_id)
            if not survey.exists():
                return json_response({'error': f'Survey not found: {survey_id}'}, status=404)

            # Check if survey is active
            if not survey.active:
                return json_response({'error': 'Survey is not active'}, status=400)

            # Create user input (survey response)
            user_input_vals = {
                'survey_id': survey.id,
                'state': 'done',
                'scoring_type': survey.scoring_type,
            }

            # Add email if provided
            if data.get('email'):
                user_input_vals['email'] = data['email']

            # Add partner if provided
            if data.get('partner_id'):
                user_input_vals['partner_id'] = data['partner_id']

            user_input = request.env['survey.user_input'].sudo().create(user_input_vals)

            # Process answers
            questions = survey.question_ids.filtered(lambda q: not q.is_page)

            for question in questions:
                answer_key = f"question_{question.id}"

                if answer_key not in answers:
                    continue  # Skip if no answer provided for this question

                answer_value = answers[answer_key]

                # Validate answer value
                is_valid, error_msg = validate_answer_value(question, answer_value)
                if not is_valid:
                    return json_response({'error': error_msg}, status=400)

                # Create answer line based on question type
                answer_vals = {
                    'user_input_id': user_input.id,
                    'question_id': question.id,
                    'survey_id': survey.id,
                }

                if question.question_type == 'simple_choice':
                    # Find suggested answer by value
                    suggested_answer = question.suggested_answer_ids.filtered(
                        lambda a: a.value == answer_value
                    )
                    if suggested_answer:
                        answer_vals['suggested_answer_id'] = suggested_answer[0].id
                        answer_vals['answer_type'] = 'suggestion'
                    else:
                        answer_vals['value_char_box'] = str(answer_value)
                        answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'multiple_choice':
                    # For multiple choice, create multiple lines
                    if isinstance(answer_value, list) and answer_value:
                        created_lines = False
                        for val in answer_value:
                            suggested_answer = question.suggested_answer_ids.filtered(
                                lambda a: a.value == val
                            )
                            if suggested_answer:
                                line_vals = answer_vals.copy()
                                line_vals['suggested_answer_id'] = suggested_answer[0].id
                                line_vals['answer_type'] = 'suggestion'
                                request.env['survey.user_input.line'].sudo().create(line_vals)
                                created_lines = True
                        if created_lines:
                            continue  # Skip creating answer_vals below
                    # If no lines created, store as comma-separated values
                    if isinstance(answer_value, list):
                        answer_vals['value_char_box'] = ', '.join(str(v) for v in answer_value)
                    else:
                        answer_vals['value_char_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'text_box':
                    answer_vals['value_text_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'text_box'

                elif question.question_type == 'char_box':
                    answer_vals['value_char_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'numerical_box':
                    try:
                        answer_vals['value_numerical_box'] = float(answer_value)
                        answer_vals['answer_type'] = 'numerical_box'
                    except (ValueError, TypeError):
                        answer_vals['value_char_box'] = str(answer_value)
                        answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'date':
                    answer_vals['value_date'] = answer_value
                    answer_vals['answer_type'] = 'date'

                elif question.question_type == 'datetime':
                    answer_vals['value_datetime'] = answer_value
                    answer_vals['answer_type'] = 'datetime'

                else:
                    # Default: store as char
                    answer_vals['value_char_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'char_box'

                # Create the answer line (skip if already created for multiple_choice)
                if 'suggested_answer_id' in answer_vals or any(k.startswith('value_') for k in answer_vals.keys()):
                    request.env['survey.user_input.line'].sudo().create(answer_vals)

            # Calculate score if applicable
            if survey.scoring_type != 'no_scoring':
                user_input._mark_done()

            return json_response({
                'success': True,
                'user_input_id': user_input.id,
                'message': 'Survey submitted successfully',
                'survey_title': survey.title,
                'submitted_at': datetime.now().isoformat(),
            })

        except json.JSONDecodeError:
            return json_response({'error': 'Invalid JSON format'}, status=400)

        except Exception as e:
            _logger.error('Error in submit_survey: %s', str(e), exc_info=True)
            return json_response({'error': str(e)}, status=500)

    @http.route('/api/survey/<int:survey_id>/info', type='http', auth='public', methods=['GET'], csrf=False)
    def get_survey_info(self, survey_id, **kwargs):
        """
        Get survey information including questions
        GET /api/survey/<survey_id>/info

        Returns survey structure for API integration
        """
        if request.httprequest.method == 'OPTIONS':
            return json_response({'status': 'ok'}, status=200)
        try:
            survey = request.env['survey.survey'].sudo().browse(survey_id)
            if not survey.exists():
                return json_response({'error': f'Survey not found: {survey_id}'}, status=404)

            questions_data = []
            for question in survey.question_ids.filtered(lambda q: not q.is_page):
                q_data = {
                    'question_id': question.id,
                    'answer_key': f'question_{question.id}',
                    'title': question.title,
                    'question_type': question.question_type,
                    'is_mandatory': getattr(question, 'is_mandatory', getattr(question, 'constr_mandatory', False)),
                }

                # Add options for choice questions
                if question.question_type in ['simple_choice', 'multiple_choice']:
                    q_data['options'] = [
                        {'id': ans.id, 'value': ans.value}
                        for ans in question.suggested_answer_ids
                    ]

                questions_data.append(q_data)

            return json_response({
                'survey_id': survey.id,
                'title': survey.title,
                'description': survey.description or '',
                'active': survey.active,
                'question_count': len(questions_data),
                'questions': questions_data,
            })

        except Exception as e:
            _logger.error('Error in get_survey_info: %s', str(e), exc_info=True)
            return json_response({'error': str(e)}, status=500)

    @http.route('/api/survey/<int:survey_id>/participations', type='http', auth='public', methods=['GET'], csrf=False)
    def get_survey_participations(self, survey_id, **kwargs):
        """
        Get survey participations (responses)
        GET /api/survey/<survey_id>/participations

        Query Parameters:
            - email: Filter by email (optional)
            - partner_id: Filter by partner_id (optional)
            - question_{id}: Filter by answer to specific question (optional, can have multiple)
              Example: ?question_74=abc@gmail.com&question_75=John

        Returns list of participations with user_input_id for updating
        """
        if request.httprequest.method == 'OPTIONS':
            return json_response({'status': 'ok'}, status=200)
        try:
            # Find survey
            survey = request.env['survey.survey'].sudo().browse(survey_id)
            if not survey.exists():
                return json_response({'error': f'Survey not found: {survey_id}'}, status=404)

            # Build domain for searching user inputs
            domain = [('survey_id', '=', survey_id)]

            # Add filters if provided
            email = kwargs.get('email')
            partner_id = kwargs.get('partner_id')

            if email:
                domain.append(('email', '=', email))

            if partner_id:
                try:
                    domain.append(('partner_id', '=', int(partner_id)))
                except (ValueError, TypeError):
                    return json_response({'error': 'Invalid partner_id'}, status=400)

            # Search user inputs
            user_inputs = request.env['survey.user_input'].sudo().search(domain, order='create_date desc')

            # Filter by question answers if provided
            question_filters = {}
            for key, value in kwargs.items():
                if key.startswith('question_'):
                    try:
                        question_id = int(key.replace('question_', ''))
                        question_filters[question_id] = value
                    except (ValueError, TypeError):
                        continue

            # Apply question filters
            if question_filters:
                filtered_user_inputs = request.env['survey.user_input'].sudo()

                for user_input in user_inputs:
                    match_all = True

                    # Check if this user_input matches all question filters
                    for question_id, search_value in question_filters.items():
                        # Find answer lines for this question and user_input
                        answer_lines = request.env['survey.user_input.line'].sudo().search([
                            ('user_input_id', '=', user_input.id),
                            ('question_id', '=', question_id)
                        ])

                        if not answer_lines:
                            match_all = False
                            break

                        # Check if any answer line matches the search value
                        found_match = False
                        for line in answer_lines:
                            # Check all possible value fields
                            answer_value = None

                            if line.value_char_box:
                                answer_value = line.value_char_box
                            elif line.value_text_box:
                                answer_value = line.value_text_box
                            elif line.value_numerical_box:
                                answer_value = str(line.value_numerical_box)
                            elif line.value_date:
                                answer_value = str(line.value_date)
                            elif line.value_datetime:
                                answer_value = str(line.value_datetime)
                            elif line.suggested_answer_id:
                                answer_value = line.suggested_answer_id.value

                            # Case-insensitive comparison
                            if answer_value and str(search_value).lower() in str(answer_value).lower():
                                found_match = True
                                break

                        if not found_match:
                            match_all = False
                            break

                    if match_all:
                        filtered_user_inputs |= user_input

                user_inputs = filtered_user_inputs

            # Format response
            participations = []
            for user_input in user_inputs:
                # Get all answers for this participation
                answers = {}
                for line in user_input.user_input_line_ids:
                    question_key = f"question_{line.question_id.id}"

                    # Get the answer value based on question type
                    answer_value = None
                    if line.suggested_answer_id:
                        answer_value = line.suggested_answer_id.value
                    elif line.value_text_box:
                        answer_value = line.value_text_box
                    elif line.value_char_box:
                        answer_value = line.value_char_box
                    elif line.value_numerical_box:
                        answer_value = line.value_numerical_box
                    elif line.value_date:
                        answer_value = str(line.value_date)
                    elif line.value_datetime:
                        answer_value = str(line.value_datetime)

                    # For multiple choice questions, collect all answers
                    if question_key in answers:
                        # Convert to list if not already
                        if not isinstance(answers[question_key], list):
                            answers[question_key] = [answers[question_key]]
                        answers[question_key].append(answer_value)
                    else:
                        answers[question_key] = answer_value

                participation_data = {
                    'user_input_id': user_input.id,
                    'email': user_input.email or '',
                    'partner_id': user_input.partner_id.id if user_input.partner_id else None,
                    'partner_name': user_input.partner_id.name if user_input.partner_id else '',
                    'state': user_input.state,
                    'create_date': user_input.create_date.isoformat() if user_input.create_date else '',
                    'scoring_total': user_input.scoring_total if hasattr(user_input, 'scoring_total') else 0,
                    'answers': answers,
                }
                participations.append(participation_data)

            return json_response({
                'success': True,
                'survey_id': survey.id,
                'survey_title': survey.title,
                'total_participations': len(participations),
                'participations': participations,
            })

        except Exception as e:
            _logger.error('Error in get_survey_participations: %s', str(e), exc_info=True)
            return json_response({'error': str(e)}, status=500)

    @http.route('/api/survey/response/<int:user_input_id>', type='http', auth='public', methods=['PUT'], csrf=False)
    def update_survey_response(self, user_input_id, **kwargs):
        """
        Update existing survey response via API
        PUT /api/survey/response/<user_input_id>

        Body: {
            "answers": {
                "question_1": "New Answer 1",
                "question_2": ["New Option 1", "New Option 2"],
                ...
            }
        }

        Returns: {
            "success": true,
            "user_input_id": 42,
            "message": "Survey response updated successfully"
        }
        """
        if request.httprequest.method == 'OPTIONS':
            return json_response({'status': 'ok'}, status=200)
        try:
            # Parse request body
            data = json.loads(request.httprequest.data.decode('utf-8'))
            answers = data.get('answers', {})

            if not answers:
                return json_response({'error': 'Missing answers'}, status=400)

            # Find user input
            user_input = request.env['survey.user_input'].sudo().browse(user_input_id)
            if not user_input.exists():
                return json_response({'error': f'Survey response not found: {user_input_id}'}, status=404)

            survey = user_input.survey_id

            # Only delete answer lines for questions that are being updated
            question_ids_to_update = []
            for key in answers.keys():
                if key.startswith('question_'):
                    try:
                        question_id = int(key.replace('question_', ''))
                        question_ids_to_update.append(question_id)
                    except (ValueError, TypeError):
                        continue

            # Delete only the answer lines for questions being updated
            if question_ids_to_update:
                lines_to_delete = request.env['survey.user_input.line'].sudo().search([
                    ('user_input_id', '=', user_input.id),
                    ('question_id', 'in', question_ids_to_update)
                ])
                lines_to_delete.unlink()

            # Process new answers (only for questions in payload)
            questions = survey.question_ids.filtered(lambda q: not q.is_page)

            for question in questions:
                answer_key = f"question_{question.id}"

                if answer_key not in answers:
                    continue  # Keep existing answer if not in payload

                answer_value = answers[answer_key]

                # Validate answer value
                is_valid, error_msg = validate_answer_value(question, answer_value)
                if not is_valid:
                    return json_response({'error': error_msg}, status=400)

                # Create answer line based on question type
                answer_vals = {
                    'user_input_id': user_input.id,
                    'question_id': question.id,
                    'survey_id': survey.id,
                }

                if question.question_type == 'simple_choice':
                    suggested_answer = question.suggested_answer_ids.filtered(
                        lambda a: a.value == answer_value
                    )
                    if suggested_answer:
                        answer_vals['suggested_answer_id'] = suggested_answer[0].id
                        answer_vals['answer_type'] = 'suggestion'
                    else:
                        answer_vals['value_char_box'] = str(answer_value)
                        answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'multiple_choice':
                    if isinstance(answer_value, list) and answer_value:
                        created_lines = False
                        for val in answer_value:
                            suggested_answer = question.suggested_answer_ids.filtered(
                                lambda a: a.value == val
                            )
                            if suggested_answer:
                                line_vals = answer_vals.copy()
                                line_vals['suggested_answer_id'] = suggested_answer[0].id
                                line_vals['answer_type'] = 'suggestion'
                                request.env['survey.user_input.line'].sudo().create(line_vals)
                                created_lines = True
                        if created_lines:
                            continue
                    if isinstance(answer_value, list):
                        answer_vals['value_char_box'] = ', '.join(str(v) for v in answer_value)
                    else:
                        answer_vals['value_char_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'text_box':
                    answer_vals['value_text_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'text_box'

                elif question.question_type == 'char_box':
                    answer_vals['value_char_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'numerical_box':
                    try:
                        answer_vals['value_numerical_box'] = float(answer_value)
                        answer_vals['answer_type'] = 'numerical_box'
                    except (ValueError, TypeError):
                        answer_vals['value_char_box'] = str(answer_value)
                        answer_vals['answer_type'] = 'char_box'

                elif question.question_type == 'date':
                    answer_vals['value_date'] = answer_value
                    answer_vals['answer_type'] = 'date'

                elif question.question_type == 'datetime':
                    answer_vals['value_datetime'] = answer_value
                    answer_vals['answer_type'] = 'datetime'

                else:
                    answer_vals['value_char_box'] = str(answer_value)
                    answer_vals['answer_type'] = 'char_box'

                if 'suggested_answer_id' in answer_vals or any(k.startswith('value_') for k in answer_vals.keys()):
                    request.env['survey.user_input.line'].sudo().create(answer_vals)

            # Recalculate score if applicable
            if survey.scoring_type != 'no_scoring':
                user_input._mark_done()

            return json_response({
                'success': True,
                'user_input_id': user_input.id,
                'message': 'Survey response updated successfully',
                'survey_title': survey.title,
                'updated_at': datetime.now().isoformat(),
            })

        except json.JSONDecodeError:
            return json_response({'error': 'Invalid JSON format'}, status=400)

        except Exception as e:
            _logger.error('Error in update_survey_response: %s', str(e), exc_info=True)
            return json_response({'error': str(e)}, status=500)

    # ========== CORS Preflight Handlers ==========

    @http.route([
        '/api/survey/<int:survey_id>/submit',
        '/api/survey/<int:survey_id>/info',
        '/api/survey/<int:survey_id>/participations',
    ], type='http', auth='public', methods=['OPTIONS'], csrf=False)
    def survey_options(self, survey_id, **kwargs):
        """Handle CORS preflight for survey endpoints"""
        return json_response({'status': 'ok'}, status=200)

    @http.route('/api/survey/response/<int:user_input_id>', type='http', auth='public', methods=['OPTIONS'], csrf=False)
    def update_response_options(self, user_input_id, **kwargs):
        """Handle CORS preflight for update response endpoint"""
        return json_response({'status': 'ok'}, status=200)

# -*- coding: utf-8 -*-

from odoo import models, fields, api
import json


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    api_submit_endpoint = fields.Char(string='Submit API Endpoint (POST)', compute='_compute_api_info')
    api_update_endpoint = fields.Char(string='Update API Endpoint (PUT)', compute='_compute_api_info')
    api_info_endpoint = fields.Char(string='Info API Endpoint (GET)', compute='_compute_api_info')
    api_participations_endpoint = fields.Char(string='Get Participations Endpoint (GET)', compute='_compute_api_info')
    sample_payload = fields.Text(string='Sample JSON Payload', compute='_compute_api_info')

    mail_to_employee_ids = fields.Many2many(
        'hr.employee',
        'survey_employee_notification_rel',
        'survey_id',
        'employee_id',
        string='Mail to',
        help='Send email notification to these employees when a new survey response is submitted'
    )

    # Compatibility field for views that might reference it
    certification_validity_months = fields.Integer(
        string='Certification Validity (Months)',
        default=0,
        help='Compatibility field - not used in this module'
    )

    @api.depends('question_ids')
    def _compute_api_info(self):
        """Generate API endpoints and sample payload"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            # API endpoints with HTTP methods
            record.api_submit_endpoint = f"POST {base_url}/api/survey/{record.id}/submit"
            record.api_update_endpoint = f"PUT {base_url}/api/survey/response/<user_input_id>"
            record.api_info_endpoint = f"GET {base_url}/api/survey/{record.id}/info"
            record.api_participations_endpoint = f"GET {base_url}/api/survey/{record.id}/participations"

            # Generate sample payload
            record.sample_payload = self._generate_sample_payload(record)

    def _generate_sample_payload(self, survey):
        """Generate sample JSON payload based on survey questions"""
        payload = {
            'survey_id': survey.id,
            'answers': {}
        }

        # Get all questions (exclude pages)
        questions = survey.question_ids.filtered(lambda q: not q.is_page)

        for question in questions:
            answer_key = f"question_{question.id}"

            # Generate sample answer based on question type
            if question.question_type == 'simple_choice':
                if question.suggested_answer_ids:
                    payload['answers'][answer_key] = question.suggested_answer_ids[0].value
                else:
                    payload['answers'][answer_key] = "Option 1"

            elif question.question_type == 'multiple_choice':
                if question.suggested_answer_ids:
                    payload['answers'][answer_key] = [ans.value for ans in question.suggested_answer_ids[:2]]
                else:
                    payload['answers'][answer_key] = ["Option 1", "Option 2"]

            elif question.question_type == 'text_box':
                payload['answers'][answer_key] = "Sample text answer"

            elif question.question_type == 'char_box':
                payload['answers'][answer_key] = "Short answer"

            elif question.question_type == 'numerical_box':
                payload['answers'][answer_key] = 5

            elif question.question_type == 'date':
                payload['answers'][answer_key] = "2025-11-22"

            elif question.question_type == 'datetime':
                payload['answers'][answer_key] = "2025-11-22 12:00:00"

            else:
                payload['answers'][answer_key] = "Sample answer"

        return json.dumps(payload, indent=2, ensure_ascii=False)

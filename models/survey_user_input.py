# -*- coding: utf-8 -*-

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    def write(self, vals):
        """Override write to send email when survey is marked as done"""
        result = super(SurveyUserInput, self).write(vals)

        # Send email notification when state changes to 'done'
        if vals.get('state') == 'done':
            for user_input in self:
                # Use with_delay if available, otherwise send immediately
                try:
                    # Commit the transaction to ensure answer lines are saved
                    self.env.cr.commit()
                    self._send_notification_email(user_input)
                except Exception as e:
                    _logger.error(f"Error triggering email notification: {str(e)}", exc_info=True)

        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to send email notification to employees"""
        user_inputs = super(SurveyUserInput, self).create(vals_list)

        # Send email for records created with state='done'
        for user_input in user_inputs:
            if user_input.state == 'done':
                # Delay email to ensure answer lines are committed
                try:
                    # Flush to ensure all data is written to database
                    self.env.flush_all()
                    self._send_notification_email(user_input)
                except Exception as e:
                    _logger.error(f"Error triggering email notification: {str(e)}", exc_info=True)

        return user_inputs

    def _send_notification_email(self, user_input):
        """Send email notification to employees specified in survey"""
        try:
            survey = user_input.survey_id

            # Check if survey has employees to notify
            if not survey.mail_to_employee_ids:
                return

            # Get employee emails
            recipient_emails = survey.mail_to_employee_ids.mapped('work_email')
            recipient_emails = [email for email in recipient_emails if email]  # Filter out empty emails

            if not recipient_emails:
                _logger.warning(f"Survey {survey.id} has employees but no valid work emails")
                return

            # Build email body with Question: Answer format
            email_body = self._build_email_body(user_input)

            # Send email using Odoo mail system
            mail_values = {
                'subject': f'New Survey Response: {survey.title}',
                'body_html': email_body,
                'email_to': ', '.join(recipient_emails),
                'email_from': self.env.company.email or 'noreply@intellisyncdata.com',
                'auto_delete': False,
            }

            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()

            _logger.info(f"Survey response notification sent to {len(recipient_emails)} employees for survey {survey.id}")

        except Exception as e:
            _logger.error(f"Error sending survey notification email: {str(e)}", exc_info=True)

    def _build_email_body(self, user_input):
        """Build HTML email body with Question: Answer format"""
        survey = user_input.survey_id

        # Refresh to get latest answer lines
        user_input.invalidate_recordset(['user_input_line_ids'])

        # Email header
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
            <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
                New Survey Response Received
            </h2>

            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 5px 0;"><strong>Survey:</strong> {survey.title}</p>
                <p style="margin: 5px 0;"><strong>Submitted by:</strong> {user_input.email or 'Anonymous'}</p>
                <p style="margin: 5px 0;"><strong>Submission Date:</strong> {user_input.create_date.strftime('%Y-%m-%d %H:%M:%S') if user_input.create_date else 'N/A'}</p>
            </div>

            <h3 style="color: #2c3e50; margin-top: 30px;">Responses:</h3>
            <div style="background-color: #ffffff; border: 1px solid #dee2e6; border-radius: 5px; padding: 20px;">
        """

        # Get all answer lines grouped by question
        questions_answered = {}
        answer_lines = user_input.user_input_line_ids

        _logger.info(f"Building email for user_input {user_input.id}, found {len(answer_lines)} answer lines")

        for line in answer_lines:
            question = line.question_id
            if question.id not in questions_answered:
                questions_answered[question.id] = {
                    'question': question,
                    'answers': []
                }

            # Get answer value
            answer_value = None
            if line.suggested_answer_id:
                answer_value = line.suggested_answer_id.value
            elif line.value_text_box:
                answer_value = line.value_text_box
            elif line.value_char_box:
                answer_value = line.value_char_box
            elif line.value_numerical_box:
                answer_value = str(line.value_numerical_box)
            elif line.value_date:
                answer_value = str(line.value_date)
            elif line.value_datetime:
                answer_value = str(line.value_datetime)

            if answer_value:
                questions_answered[question.id]['answers'].append(answer_value)

        # Check if we have any answers
        if not questions_answered:
            html += """
            <p style="color: #6c757d; text-align: center; padding: 20px;">
                No responses recorded yet. This may be due to timing issues.
            </p>
            """
        else:
            # Format each question and answer
            for q_id, q_data in questions_answered.items():
                question = q_data['question']
                answers = q_data['answers']

                html += f"""
                <div style="margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #e9ecef;">
                    <p style="margin: 0 0 10px 0; color: #495057; font-weight: bold;">
                        {question.title}
                    </p>
                    <div style="margin-left: 20px; color: #212529;">
                """

                # Format answer based on number of answers (for multiple choice)
                if len(answers) > 1:
                    html += "<ul style='margin: 5px 0; padding-left: 20px;'>"
                    for answer in answers:
                        html += f"<li>{answer}</li>"
                    html += "</ul>"
                else:
                    # Preserve newlines for text answers
                    answer_text = answers[0] if answers else 'No answer'
                    answer_text = str(answer_text).replace('\n', '<br>')
                    html += f"<p style='margin: 5px 0;'>{answer_text}</p>"

                html += """
                    </div>
                </div>
                """

        # Email footer
        html += f"""
            </div>

            <div style="margin-top: 30px; padding: 15px; background-color: #e9ecef; border-radius: 5px; text-align: center;">
                <p style="margin: 0; color: #6c757d; font-size: 12px;">
                    This is an automated notification from IntelliSync Survey System
                </p>
            </div>
        </div>
        """

        return html

import os  # Standard library
from flask import Flask, render_template, request, redirect, url_for, session
from g4f.client import Client  # GPT-based client

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key

client = Client()

# Function to summarize text in Filipino using GPT
def generate_summary(text):
    if len(text.split()) < 200:
        return "Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 200 salita."

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f"Summarize this text in Filipino (make sure to keep the main points in the text):\n\n{text}"}],
        )

        if not response.choices:
            return "No summary could be generated."

        return response.choices[0].message.content.strip() or "No summary could be generated."

    except Exception as e:
        return f"An error occurred during summarization: {str(e)}"

# Grade essay functionality
def grade_essay(essay_text, context_text):
    if len(essay_text.split()) < 200:
        return "Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 200 salita."

    criteria = session.get('criteria', [])
    if not criteria:
        return "No criteria set for grading."

    total_points_possible = session.get('total_points_possible', 0)
    total_points_received = 0
    justifications = {}  # Store justifications for each criterion

    for criterion in criteria:
        truncated_essay = essay_text[:1000]  # Limit the essay text to a maximum length
        detailed_breakdown = criterion['detailed_breakdown']  # Retrieve detailed breakdown

        # Adjusted prompt to include detailed breakdown
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user",
                       "content": f"Grade the following essay based on the criterion '{criterion['name']}' out of {criterion['points_possible']} points. (Do not be too strict when grading.) "
                                  f"Use the following context to help inform your grading:\n\n{context_text}\n\n"
                                  f"Here is the detailed breakdown for this criterion:\n\n{detailed_breakdown}\n\n"
                                  f"Essay:\n{truncated_essay}\n\n"
                                  f"Respond in this format: Score: [numeric value]/{criterion['points_possible']} Justification: [justification (20 words max)]"}],
        )

        if not response.choices:
            return "No grade could be generated."

        raw_grade = response.choices[0].message.content.strip()

        # Debugging: Print raw response to inspect its format
        print(f"Raw GPT response: {raw_grade}")

        # Extract score from response using more robust parsing
        if "Score:" in raw_grade:
            try:
                # Attempt to parse score and justification
                score_part = raw_grade.split("Score:")[1].split("/")[0].strip()
                points_received = float(score_part)  # Use float to allow decimal values
                justification = raw_grade.split("Justification:")[1].strip() if "Justification:" in raw_grade else "No justification provided."
                
                justifications[criterion['name']] = justification
                total_points_received += points_received
            except (ValueError, IndexError) as e:
                # Debugging: Log any parsing errors
                print(f"Error while parsing: {e}")
                return f"Invalid grade format received: {raw_grade}"
        else:
            # If the response doesn't contain the expected "Score:" format, return an error
            return f"Invalid grade format received: {raw_grade}"

    if total_points_possible == 0:
        return "No valid criteria to grade the essay."

    # Calculate percentage and letter grade
    percentage = (total_points_received / total_points_possible) * 100
    letter_grade = (
        "A+" if percentage >= 98 else
        "A" if percentage >= 95 else
        "A-" if percentage >= 93 else
        "B+" if percentage >= 90 else
        "B" if percentage >= 85 else
        "B-" if percentage >= 83 else
        "C+" if percentage >= 80 else
        "C" if percentage >= 78 else
        "D" if percentage >= 75 else "F"
    )

    justification_summary = "\n".join([f"{criterion['name']}: {justifications[criterion['name']]}" for criterion in criteria if criterion['name'] in justifications])

    return (f"Draft Grade: {letter_grade}\n"
            f"Draft Score: {total_points_received}/{total_points_possible}\n\n"
            f"Justifications:\n{justification_summary}")

@app.route('/process', methods=['POST'])
def process_essay():
    essay = request.form['essay']
    context = request.form['context']  # Get context text from the form
    session['original_text'] = essay  # Store the original text in the session
    session['context_text'] = context  # Store the context text in the session

    if len(essay.split()) < 200:
        return render_template('index.html', essay=essay,
                               error="Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 200 salita.")

    if not context.strip():  # Check if context is empty or just whitespace
        return render_template('index.html', essay=essay,
                               error="Error: Please provide context for grading.")

    return redirect(url_for('set_criteria'))

@app.route('/set_criteria', methods=['GET', 'POST'])
def set_criteria():
    if request.method == 'POST':
        criterion_name = request.form['criterion_name']
        weight = float(request.form['weight']) / 100  # Convert percentage to decimal
        points_possible = float(request.form['points_possible'])  # Ensure it's treated as a float
        detailed_breakdown = request.form['detailed_breakdown']  # Get the detailed breakdown text

        if 'criteria' not in session:
            session['criteria'] = []
            session['total_points_possible'] = 0  # Initialize total points

        current_total_weight = sum(criterion['weight'] for criterion in session['criteria']) + weight

        if current_total_weight > 1.0:
            return render_template('set_criteria.html', essay=session.get('original_text', ''), error="Total weight cannot exceed 100% (1.0). Please adjust your weights.")

        # Append new criterion with the detailed breakdown
        session['criteria'].append({
            'name': criterion_name,
            'weight': weight,
            'points_possible': points_possible,
            'detailed_breakdown': detailed_breakdown  # Store detailed breakdown
        })

        # Update total points possible
        session['total_points_possible'] += points_possible

        return render_template('set_criteria.html', essay=session.get('original_text', ''),
                               criteria=session['criteria'], total_points_possible=session['total_points_possible'])

    original_text = session.get('original_text', '')
    criteria = session.get('criteria', [])
    total_possible_points = session.get('total_points_possible', 0)

    return render_template('set_criteria.html', essay=original_text, criteria=criteria, 
                           total_points_possible=total_possible_points)

@app.route('/reset_criteria', methods=['POST'])
def reset_criteria():
    session.pop('criteria', None)  # Clear criteria from the session
    session.pop('total_points_possible', None)  # Clear total points possible
    return redirect(url_for('set_criteria'))

@app.route('/results', methods=['GET'])
def grade():
    original_text = session.get('original_text', '')
    context_text = session.get('context_text', '')  # Retrieve context text from the session
    summary = generate_summary(original_text)
    grades = grade_essay(original_text, context_text)  # Pass context text to the grading function
    return render_template('results.html', summary=summary, grade=grades, essay=original_text)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)

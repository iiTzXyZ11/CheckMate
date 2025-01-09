import os  # Standard library
import re
from flask import Flask, render_template, redirect, url_for, request, session
from g4f.client import Client  # GPT-based client
from g4f.Provider import GeminiPro


app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key

# Initialize the GPT client for text generation and grading
client = Client()
image_to_text_client = Client(api_key="AIzaSyDKnjQPE-x6cJGDbsjX3lBGa5V3tp0WArQ", provider=GeminiPro)

# Model router function to select the appropriate model
def model_router(task_type, text):
    # Determine model based on task type and length of text
    if task_type == "summary" and len(text.split()) > 500:
        return "gpt-4o"
    elif task_type == "summary" and len(text.split()) <= 500:
        return "gpt-4"
    elif task_type == "grading":
        return "gpt-4o"
    return "gpt-4"  # Default fallback model

# Function to convert image to text
def image_to_text(image_file):
    try:
        print(f"Received the image: {image_file.filename}")
        
        response = image_to_text_client.chat.completions.create(
            model="gemini-1.5-pro-latest",
            messages=[{"role": "user", "content": "extract the text from this image"}],
            image=image_file
        )
        
        if hasattr(response, 'choices') and len(response.choices) > 0: # type: ignore
            content = response.choices[0].message.content # type: ignore
            print(f"Extracted content: {content}")
            return content.strip() if content else "No text could be extracted."
        return "No text could be extracted."
    
    except Exception as e:
        print(f"Error during image processing: {e}")
        return f"An error occurred during image processing: {str(e)}"

# Function to summarize text in Filipino
def generate_summary(text):
    if len(text.split()) < 150:
        return "Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 150 salita."

    try:
        model = model_router("summary", text)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"Summarize this text in Filipino:\n\n{text}",}]
            
        )

        if not response.choices: # type: ignore
            print("No choices in response for summary.")
            return "No summary could be generated."

        summary_content = response.choices[0].message.content.strip() # type: ignore
        print(f"Generated summary: {summary_content}")
        return summary_content or "No summary could be generated."

    except Exception as e:
        print(f"Error during summary generation: {e}")
        return f"An error occurred during summarization: {str(e)}"

# Grade essay function
def grade_essay(essay_text, context_text):
    # Check essay length once, early return if too short
    if len(essay_text.split()) < 150:
        return "Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 150 salita."

    # Retrieve criteria and total points
    criteria = session.get('criteria', [])
    if not criteria:
        return "No criteria set for grading."

    total_points_possible = session.get('total_points_possible', 0)
    if total_points_possible == 0:
        return "No valid criteria to grade the essay."

    total_points_received = 0
    justifications = {}

    # Collect grades per criterion
    grades_per_criterion = []
    
    # Compile the regular expression pattern for grade and justification extraction
    grade_pattern = re.compile(r"Grade:\s*(\d+(\.\d+)?)\/(\d+)")
    justification_pattern = re.compile(r"Justification:\s*(.*)")

    for criterion in criteria:
        truncated_essay = essay_text[:1000]  # Limit essay length for context

        # Modify the prompt for grading
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": (f"Grade the following essay based on the criterion '{criterion['name']}' out of "
                            f"{criterion['points_possible']} points. "
                            "Do not be too strict when grading. Consider the context and criteria. "
                            f"Essay:\n{truncated_essay}\n\n"
                            f"Use the context below to inform your grading:\n\n{context_text}\n\n"
                            f"Provide the grade for this criterion in the following format: "
                            f"Grade: [numeric value]/{criterion['points_possible']} Justification: [brief justification (max 20 words)].")
            }]
        )

        # Validate response
        if not hasattr(response, 'choices') or len(response.choices) == 0:  # type: ignore
            return f"Invalid response received for criterion '{criterion['name']}'. No choices were found."

        raw_grade = response.choices[0].message.content.strip()  # type: ignore
        print(f"Raw grade for {criterion['name']}: {raw_grade}")  # Debug print

        # Extract grade and justification using regex
        grade_match = grade_pattern.search(raw_grade)
        justification_match = justification_pattern.search(raw_grade)

        if not grade_match or not justification_match:
            return f"Invalid grade format received for criterion '{criterion['name']}'. Expected 'Grade: [score]/[total] Justification: [text]'"

        # Parse the grade and justification
        points_received = float(grade_match.group(1))
        justification = justification_match.group(1) if justification_match else "No justification provided."

        # Save the grade and justification
        justifications[criterion['name']] = justification
        total_points_received += points_received

        # Save the grade per criterion
        grades_per_criterion.append(f"Criterion: {criterion['name']} - Grade: {points_received}/{criterion['points_possible']} - Justification: {justification}")

    # Calculate total percentage and letter grade
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

    # Format the final output including grades per criterion
    justification_summary = "\n".join(grades_per_criterion)

    return (f"Draft Grade: {letter_grade}\n"
            f"Draft Score: {total_points_received}/{total_points_possible}\n\n"
            f"Justifications:\n{justification_summary}")

@app.route('/')  # Define the root URL route
def home():
    print("Home route accessed")  # Debug print
    return redirect(url_for('front_page'))  # Redirect to the front page

@app.route('/front')  # Front page route
def front_page():
    print("Front page accessed")  # Debug print
    return render_template('front_page.html')

@app.route('/scan', methods=['GET', 'POST'])  # Define the scanning route
def index():
    if request.method == 'POST':
        context = request.form['context']  # Get context text from the form
        session['context_text'] = context  # Store the context text in the session

        # Check for image upload
        image = request.files.get('image')  # Get the uploaded image
        if image:  # If an image was uploaded
            essay = image_to_text(image)  # Convert the image to text
            if "Error" in essay:  # Check if there was an error during processing
                return render_template('index.html', error=essay)
        else:
            essay = request.form['essay']  # If no image, get the text from the textarea

        # Store the original text in the session
        session['original_text'] = essay  

        # Check if the essay has at least 150 words
        if len(essay.split()) < 150:
            return render_template('index.html', essay=essay,
                                    error="Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 150 salita.")

        if not context.strip():  # Check if context is empty or just whitespace
            return render_template('index.html', essay=essay,
                                    error="Error: Please provide context for grading.")

        return redirect(url_for('set_criteria'))  # Redirect to set_criteria

    return render_template('index.html')  # Render the scanning page

@app.route('/process_essay', methods=['GET', 'POST'])  # Define the route for processing the essay
def process_essay():
    original_text = session.get('original_text', '')
    context_text = session.get('context_text', '')

    if not original_text or not context_text:
        return redirect(url_for('home'))

    # Generate summary
    summary_result = generate_summary(original_text)

    # Grade the essay based on criteria
    grade_result = grade_essay(original_text, context_text)

    return render_template('results.html', essay=original_text, summary=summary_result, grade=grade_result)

@app.route('/set_criteria', methods=['GET', 'POST'])
def set_criteria():
    if request.method == 'POST':
        # Retrieve the criterion details from the form
        criterion_name = request.form['criterion_name']
        weight = float(request.form['weight']) / 100  # Convert to fraction
        points_possible = float(request.form['points_possible'])
        detailed_breakdown = request.form['detailed_breakdown']

        # Create a new criterion entry
        new_criterion = {
            'name': criterion_name,
            'weight': weight,
            'points_possible': points_possible,
            'detailed_breakdown': detailed_breakdown
        }

        # Retrieve existing criteria from the session, or initialize if none exist
        if 'criteria' not in session:
            session['criteria'] = []
        session['criteria'].append(new_criterion)  # Add the new criterion
        session.modified = True  # Mark the session as modified

        # Recalculate total points possible
        session['total_points_possible'] = sum(criterion['points_possible'] for criterion in session['criteria'])

        return redirect(url_for('set_criteria'))  # Redirect to the same page to display updated criteria

    # Load existing criteria for the GET request
    criteria = session.get('criteria', [])
    total_points_possible = session.get('total_points_possible', 0)

    return render_template('set_criteria.html', criteria=criteria, total_points_possible=total_points_possible)

@app.route('/clear_session', methods=['POST'])
def clear_session():
    session.pop('criteria', None)  # Remove the criteria data from the session
    session.pop('total_points_possible', None)  # Remove any other session data if needed
    return redirect(url_for('set_criteria'))  # Redirect to the set criteria page


# New route for 'Contact Us'
@app.route('/contact')  # Define the contact route
def contact():
    return redirect("https://www.facebook.com/profile.php?id=61567870400304")  # Replace with your actual Facebook page URL

# New route for 'How to Use'
@app.route('/how-to-use', methods=['GET'])
def how_to_use():
    return render_template('how_to_use.html')

if __name__ == '__main__':
    app.run(debug=True)
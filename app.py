import os  # Standard library
from flask import Flask, render_template, request, redirect, url_for, session
from g4f.client import Client  # GPT-based client
from g4f.Provider.GeminiPro import GeminiPro

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate a random secret key

# Initialize the GPT client for text generation and grading
client = Client()

# Initialize a separate client for image-to-text conversion
image_to_text_client = Client(api_key="AIzaSyDKnjQPE-x6cJGDbsjX3lBGa5V3tp0WArQ", provider=GeminiPro)

# Function to convert image to text using the image-to-text model
def image_to_text(image_file):
    try:
        print(f"Received image: {image_file.filename}")
        
        response = image_to_text_client.chat.completions.create(
            model="gemini-1.5-flash",
            messages=[{"role": "user", "content": "read the text here"}],
            image=image_file  # Ensure this is correct for your API
        )

        if hasattr(response, 'choices') and len(response.choices) > 0:  # type: ignore
            content = response.choices[0].message.content  # type: ignore
            print(f"Extracted content: {content}")  # Log the extracted content
            return content.strip() if content else "No text could be extracted."
        return "No text could be extracted."
    
    except Exception as e:
        print(f"Error during image processing: {e}")  # Log the error
        return f"An error occurred during image processing: {str(e)}"

# Function to summarize text in Filipino using GPT
def generate_summary(text):
    if len(text.split()) < 200:
        return "Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 200 salita."

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": f"Summarize this text in Filipino (make sure to keep the main points in the text):\n\n{text}"}],
        )

        if not response.choices:  # type: ignore
            return "No summary could be generated."

        return response.choices[0].message.content.strip() or "No summary could be generated."  # type: ignore

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
    justifications = {}

    for criterion in criteria:
        truncated_essay = essay_text[:1000]
        detailed_breakdown = criterion['detailed_breakdown']

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user",
                        "content": f"Grade the following essay based on the criterion '{criterion['name']}' out of {criterion['points_possible']} points. (Do not be too strict when grading. Make considerations so that you wont be too strict. and make it possible to achieve a perfect score if it deserves it, but stick to the context and criteria. Respond in Filipino. And always review your grading) "
                                    f"Use the following context to help inform your grading:\n\n{context_text}\n\n"
                                    f"Here is the detailed breakdown for this criterion:\n\n{detailed_breakdown}\n\n"
                                    f"Essay:\n{truncated_essay}\n\n"
                                    f"Respond in this format: Score: [numeric value]/{criterion['points_possible']} Justification: [justification (20 words max)]"}],
        )

        if not hasattr(response, 'choices') or len(response.choices) == 0:  # type: ignore
            return f"Invalid response received for criterion '{criterion['name']}'. No choices were found."

        raw_grade = response.choices[0].message.content if response.choices[0].message.content is not None else ""  # type: ignore
        raw_grade = raw_grade.strip()

        if "Score:" in raw_grade:
            try:
                score_part = raw_grade.split("Score:")[1].split("/")[0].strip()
                points_received = float(score_part)
                justification = raw_grade.split("Justification:")[1].strip() if "Justification:" in raw_grade else "No justification provided."
                
                justifications[criterion['name']] = justification
                total_points_received += points_received
            except (ValueError, IndexError) as e:
                print(f"Error while parsing: {e}")
                return f"Invalid grade format received: {raw_grade}"
        else:
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

        # Check if the essay has at least 200 words
        if len(essay.split()) < 200:
            return render_template('index.html', essay=essay,
                                error="Error: Ang input na teksto ay dapat magkaroon ng hindi bababa sa 200 salita.")

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
        criterion_name = request.form['criterion_name']
        weight = float(request.form['weight']) / 100  # Convert whole number to decimal (e.g., 50 becomes 0.5)
        points_possible = float(request.form['points_possible'])
        detailed_breakdown = request.form['detailed_breakdown']

        new_criterion = {
            'name': criterion_name,
            'weight': weight,  # Store as a decimal for backend processing
            'points_possible': points_possible,
            'detailed_breakdown': detailed_breakdown
        }

        # Store criteria in session
        if 'criteria' not in session:
            session['criteria'] = []
        session['criteria'].append(new_criterion)

        # Calculate total points possible
        session['total_points_possible'] = session.get('total_points_possible', 0) + points_possible

        return redirect(url_for('set_criteria'))  # Redirect to the same page to add more criteria

    return render_template('set_criteria.html')  # Render the set criteria page

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

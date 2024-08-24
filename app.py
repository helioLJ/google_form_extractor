import json
import sys
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementClickInterceptedException, ElementNotInteractableException
from bs4 import BeautifulSoup
from selenium.webdriver.common.keys import Keys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_questions(html_content):
    logging.info("Extracting questions from HTML content")
    soup = BeautifulSoup(html_content, 'html.parser')
    questions = []

    question_containers = soup.find_all('div', class_='Qr7Oae')
    logging.info(f"Found {len(question_containers)} question containers")

    for container in question_containers:
        question_text_elem = container.find('span', class_='M7eMe')
        if question_text_elem:
            question_text = question_text_elem.text.strip()
            required = container.find('span', class_='vnumgf') is not None

            options = []
            if container.find('input', {'type': 'text'}):
                question_type = 'Short answer'
            elif container.find('input', {'type': 'date'}):
                question_type = 'Date'
            elif container.find('input', {'type': 'email'}):
                question_type = 'Email'
            elif container.find('textarea'):
                question_type = 'Long answer'
            elif container.find('div', {'role': 'radiogroup'}):
                question_type = 'Multiple choice'
                options = [option.text.strip() for option in container.find_all('span', class_='aDTYNe')]
            elif container.find('div', {'role': 'checkbox'}):
                question_type = 'Checkbox'
                options = [option.text.strip() for option in container.find_all('span', class_='aDTYNe')]
            else:
                question_type = 'Unknown'
            
            questions.append({
                'question': question_text,
                'required': required,
                'type': question_type,
                'options': options if options else None
            })
            logging.info(f"Extracted question: {question_text} (Type: {question_type})")

    logging.info(f"Extracted {len(questions)} questions in total")
    return questions

def extract_checkbox_options(question_container):
    checkbox_elements = question_container.find_elements(By.CSS_SELECTOR, 'div.eBFwI')
    
    options = []
    for checkbox in checkbox_elements:
        label_element = checkbox.find_element(By.CSS_SELECTOR, 'span.aDTYNe')
        if label_element:
            options.append(label_element.text.strip())
    
    return options

def extract_question_details(driver, question_container):
    question_text_elem = question_container.find_element(By.CSS_SELECTOR, 'span.M7eMe')
    question_text = question_text_elem.text.strip() if question_text_elem else "Unknown Question"
    
    required = question_container.find_elements(By.CSS_SELECTOR, 'span.vnumgf')
    is_required = len(required) > 0

    # Check if it's the "Instruments NOT used" question
    if question_text == "Instruments NOT used":
        question_type = "Checkbox"
        options = extract_checkbox_options(question_container)
    else:
        question_type = "Unknown"
        options = None

    return {
        "question": question_text,
        "required": is_required,
        "type": question_type,
        "options": options
    }

def scrape_google_form(url, output_file):
    logging.info(f"Starting to scrape Google Form: {url}")
    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized')  # Start with maximized window
    driver = webdriver.Chrome(options=options)
    
    driver.get(url)
    time.sleep(5)  # Wait for the page to load

    all_sections = []
    section_number = 1
    previous_questions = set()

    while True:
        logging.info(f"Processing section {section_number}")
        
        # Extract questions from current section
        html_content = driver.page_source
        questions = extract_questions(html_content)
        
        # Check if we've seen these questions before
        current_questions = set(q['question'] for q in questions)
        if current_questions == previous_questions:
            logging.info("Same questions found. Attempting to move to next section.")
            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[@role='button']//span[contains(text(), 'Próxima') or contains(text(), 'Next')]"))
                )
                driver.execute_script("arguments[0].click();", next_button)
                logging.info("Clicked 'Next' button. Waiting for new content...")
                time.sleep(5)  # Increased wait time
                
                # Check if content has changed
                new_html_content = driver.page_source
                if new_html_content == html_content:
                    logging.info("No new content loaded. Assuming end of form.")
                    break
                else:
                    logging.info("New content detected. Continuing to next iteration.")
                    continue
            except (TimeoutException, ElementClickInterceptedException) as e:
                logging.info("No 'Next' button found or an error occurred:", exc_info=True)
                break
        
        previous_questions = current_questions

        # Add the section with its questions
        all_sections.append({
            'section': f'Section {section_number}',
            'questions': questions
        })

        # Write the current state to the output file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_sections, f, ensure_ascii=False, indent=2)
        logging.info(f"Updated output file with {len(all_sections)} sections")

        # Check for required fields and prompt user
        required_fields = [q for q in questions if q['required']]
        if required_fields:
            print("\nRequired fields found in this section:")
            for field in required_fields:
                print(f"- {field['question']} (Type: {field['type']})")
            
            input("Please fill in the required fields in the browser window, then press Enter to continue...")

        # Check if there's a 'Next' button and click it
        try:
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@role='button']//span[contains(text(), 'Próxima') or contains(text(), 'Next')]"))
            )
            driver.execute_script("arguments[0].click();", next_button)
            logging.info("Moved to next section")
            time.sleep(3)  # Wait for the next section to load
            section_number += 1
        except (TimeoutException, ElementClickInterceptedException) as e:
            logging.info("No more sections found. This is likely the last section.")
            break

    driver.quit()
    logging.info("Finished scraping Google Form")
    return all_sections

def main():
    if len(sys.argv) != 3:
        logging.error("Incorrect number of arguments")
        print("Usage: python script.py <google_form_url> <output_file>")
        sys.exit(1)

    form_url = sys.argv[1]
    output_file = sys.argv[2] + ".json"

    logging.info(f"Scraping Google Form: {form_url}")
    extracted_sections = scrape_google_form(form_url, output_file)

    logging.info(f"Extracted sections and questions have been saved to {output_file}")

    # Print the extracted sections and questions
    print("\nPrinting extracted sections and questions:")
    for i, section in enumerate(extracted_sections, 1):
        print(f"Section {i}: {section['section']}")
        for j, q in enumerate(section['questions'], 1):
            print(f"  {j}. Question: {q['question']}")
            print(f"     Type: {q['type']}")
            print(f"     Required: {'Yes' if q['required'] else 'No'}")
            if q['options']:
                print(f"     Options: {', '.join(q['options'])}")
            print()

if __name__ == "__main__":
    main()
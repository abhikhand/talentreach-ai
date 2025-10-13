# -----------------------------------------------------------------
# 1. IMPORTS & SETUP
# -----------------------------------------------------------------
import streamlit as st
import openai
import fitz
import re
import yaml
import streamlit_authenticator as stauth
import datetime
from yaml.loader import SafeLoader
from streamlit_cookies_manager import EncryptedCookieManager # CORRECT IMPORT

# -----------------------------------------------------------------
# 2. HELPER FUNCTIONS
# -----------------------------------------------------------------

def local_css(file_name):
    """Loads a local CSS file."""
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

def extract_text_from_pdf(pdf_file):
    """Extracts text from an uploaded PDF file."""
    try:
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        return "".join(page.get_text() for page in pdf_document)
    except Exception as e:
        st.error(f"Error reading PDF file: {e}", icon="🚨")
        return None

def parse_ai_output(output_text):
    """Parses the structured output from the AI model."""
    name_match = re.search(r"\[CANDIDATE_NAME\](.*?)\[END_CANDIDATE_NAME\]", output_text, re.DOTALL)
    key_points_match = re.search(r"\[KEY_POINTS\](.*?)\[END_KEY_POINTS\]", output_text, re.DOTALL)
    messages_match = re.search(r"\[OUTREACH_MESSAGES\](.*?)\[EMAIL_MESSAGE\]", output_text, re.DOTALL)
    email_match = re.search(r"\[EMAIL_MESSAGE\](.*)", output_text, re.DOTALL)

    name = name_match.group(1).strip() if name_match else "Candidate"
    key_points = key_points_match.group(1).strip() if key_points_match else ""
    messages_raw = messages_match.group(1).strip() if messages_match else ""
    # Remove [END_OUTREACH_MESSAGES] if present
    messages_raw = messages_raw.replace('[END_OUTREACH_MESSAGES]', '').strip()
    messages = [msg.strip().lstrip('1.2.3. ') for msg in re.split(r'\n\d\.\s*', messages_raw) if msg.strip()]
    email = email_match.group(1).strip() if email_match else ""
    # Remove [END_EMAIL_MESSAGE] if present
    email = email.replace('[END_EMAIL_MESSAGE]', '').strip()
    
    # Prepend the extracted name to the key_points for display
    # We will format it properly in the display logic
    full_key_points = f"**Name:** {name}\n\n{key_points}"
    
    return {"name": name, "key_points": key_points, "short_messages": messages, "long_message": email}

# -----------------------------------------------------------------
# 3. CONFIGURATION AND INITIALIZATION
# -----------------------------------------------------------------

st.set_page_config(page_title="TalentReach AI", layout="wide")

# --- SEO meta + visible landing copy for discoverability ---
st.markdown("""
<meta name="description" content="TalentReach AI helps recruiters instantly generate personalized candidate outreach messages, long emails, and candidate summaries. Upload a resume and job description — get ready-to-send outreach in seconds.">
<meta name="keywords" content="AI recruiter tool, candidate email generator, recruitment AI, hiring outreach, talent sourcing, recruiter automation">
""", unsafe_allow_html=True)

# Optional visible short landing paragraph (helps both users & search engines)
st.markdown("""
<div style="max-width:900px; margin:20px auto 10px auto; text-align:center;">
  <h2 style="margin:0; font-weight:600;">TalentReach AI — AI Outreach for Recruiters</h2>
  <p style="color:#475569; font-size:15px;">
    Upload a candidate resume and job description, and get 3 short outreach messages, a full email draft, and a candidate summary — in seconds. Try 3 free generations.
  </p>
</div>
""", unsafe_allow_html=True)

local_css("style.css")

# --- User Authentication ---
# Manually build a new, mutable dictionary from Streamlit's secrets
# This is the definitive fix to avoid the "Secrets does not support item assignment" error.
credentials = {'usernames': {}}
for username, user_info in st.secrets['credentials']['usernames'].items():
    credentials['usernames'][username] = {
        'email': user_info['email'],
        'name': user_info['name'],
        'password': user_info['password']
    }

# Initialize the cookie manager directly with the secret key
cookies = EncryptedCookieManager(password=st.secrets['cookie']['key'])

# Initialize the authenticator with values directly from secrets
authenticator = stauth.Authenticate(
    credentials,
    st.secrets['cookie']['name'],
    st.secrets['cookie']['key'],
    st.secrets['cookie']['expiry_days']
)

# --- OpenAI Client & Prompt ---
try:
    client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception as e:
    st.error("OpenAI client error. Is your API key set in Streamlit Secrets?", icon="🚨")
    st.stop()

SYSTEM_PROMPT = """
You are an expert recruitment assistant and persuasive copywriter named "TalentReach AI." 
Your tone is professional yet enthusiastic, approachable, and genuine. The goal is to start a real conversation.
Your multi-step task is as follows:

// STEP 0: EXTRACT CANDIDATE NAME
First, find the candidate's name from the profile text. Output it enclosed in tags like this: [CANDIDATE_NAME]John Doe[END_CANDIDATE_NAME].

// STEP 1: PARSE AND STRUCTURE THE CANDIDATE'S PROFILE
Next, analyze the Candidate Profile. Extract the following information and structure it exactly in this order.
[KEY_POINTS]
**Educational Summary:**
(1-3 sentences stating their educational degree and university and educational experience).

**Experience Summary:**
(A 2-3 sentence summary of their professional background, key skills, and years of experience).

**Key Achievements:**
- (A bullet point highlighting a specific, high-impact achievement).
- (A second bullet point highlighting another key achievement).
- (A third optional bullet point highlighting another key achievement).

**Skills:**
- (A bullet point listing key technical or soft skills found in the resume).
[END_KEY_POINTS]

// STEP 2: WRITE PERSUASIVE SHORT MESSAGES
Generate three distinct outreach messages (each under 100 words) that feel genuine, warm, and conversational. The goal is to spark a reply.
Requirements for all three messages:
1. Begin with a natural greeting using the candidate’s name (e.g., “Hi [Candidate’s Name], ...”).
2. Introduce the recruiter and company in the first 1–2 sentences (e.g., “I’m [Recruiter’s first Name] from [Company Name]...”).
3. Use a personalized hook that rephrases the *impact* of one achievement (qualitative, not raw, numeric metrics). Example: instead of “reduced processing time by 50%,” say “helped systems run far more efficiently.”
4. Connect their background to the the job description and/or role.
5. Highlight a benefit for the candidate (e.g., growth opportunity, exciting projects, chance to make an impact).
6. End with a clear but low-pressure call-to-action. Each message should have a different CTA style:
   - One “interest check” (e.g., “Would you be open to hearing more?”).
   - One “quick call/chat” invite.
   - One “direct role offer” (e.g., “Would you be interested in a role at [Company] as [Role Title]?”).

Output format:
[OUTREACH_MESSAGES]
1. (Message 1 - interest check)
2. (Message 2 - quick chat invite)
3. (Message 3 - role offer)

// STEP 3: WRITE A DETAILED LONG MESSAGE (EMAIL)
Write one longer outreach message (150–200 words) structured like a professional yet personable recruiting email. The goal is to tell a story and spark genuine interest.

Requirements:
1. Provide a compelling subject line (3–7 words) that is clear, warm, and not clickbait (e.g., “Exploring opportunities at [Company]”).
2. Structure the email with a natural narrative flow:
   - Opening: Friendly greeting with candidate’s name. Introduce recruiter and company, and acknowledge the candidate’s background.
   - Middle: Weave together thier achievements/skills into a story about how they align with the company’s mission, culture, role, or job description. Use qualitative phrasing (“made systems run smoother,” “helped scale faster”), not raw, numeric metrics.
   - Candidate Benefit: Highlight what they might gain (impact, growth, projects, team, mission).
   - Closing: Invite them to take the next step with a low-pressure CTA (e.g., “Would you be open to a brief chat?”).
   - Salutation: Say "looking forward to hearing from you," new line, name, new line, company name.
3. Maintain a professional yet approachable tone throughout.
4. Do not copy résumé text directly — achievements should be rephrased naturally.

Output format:
[EMAIL_MESSAGE]
**Subject:** (Compelling subject line)

(Your email content here)
"""

# -----------------------------------------------------------------
# 4. UI COMPONENTS (MODULAR FUNCTIONS)
# -----------------------------------------------------------------

def show_header():
    """Displays the main header of the application."""
    st.markdown('''
    <div style="width:100%; padding:56px 12px 44px 12px; background: linear-gradient(180deg, #f1f5f9 0%, #ffffff 60%); border-bottom: 1px solid rgba(15,23,42,0.04);">
            <div style="max-width:980px; margin:0 auto; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px;">
                <h1 style="margin:0; font-size:48px; line-height:1.1; color:#0b1220; font-weight:600; letter-spacing:0.6px; -webkit-font-smoothing:antialiased;">TalentReach AI</h1>
                <div style="color:#475569; font-size:18px; font-weight:500;">Generate Personalized Recruiting Messages</div>
            </div>
    </div>
    ''', unsafe_allow_html=True)
    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

def show_paywall():
    """Displays the paywall with links to subscribe."""
    show_header()
    st.warning("### Your free generations are complete.")
    st.markdown("---")
    st.markdown("<h3 style='text-align: center;'>Subscribe to Continue with Unlimited Generations!</h3>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div style="text-align:center;">'
            '<div style="font-size:1.1rem; font-weight:600; margin-bottom:0.2em;">Monthly Plan</div>'
            '<div style="font-size:2rem; font-weight:700; margin-bottom:0.5em;">$9.99 / month</div>'
            '</div>', unsafe_allow_html=True)
        st.link_button("Start Monthly Plan", "https://buy.stripe.com/aFa00j9Oq1L63SmgaV2kw00", use_container_width=True)
    with col2:
        st.markdown('<div style="text-align:center;">'
            '<div style="font-size:1.1rem; font-weight:600; margin-bottom:0.2em;">Yearly Plan (Save &gt;15%!)</div>'
            '<div style="font-size:2rem; font-weight:700; margin-bottom:0.5em;">$99.99 / year</div>'
            '</div>', unsafe_allow_html=True)
        st.link_button("Start Yearly Plan", "https://buy.stripe.com/bJecN51hU1L63SmaQB2kw02", use_container_width=True)

    st.markdown("<p style='text-align: center; margin-top: 2rem;'>Already subscribed? The login form is at the top of the page.</p>", unsafe_allow_html=True)


def run_main_app():
    """Displays the main application UI and handles the generation logic."""
    show_header()
    
    if 'output' not in st.session_state:
        st.session_state.output = None

    left_col, right_col = st.columns([1.2, 1])
    
    # --- LEFT COLUMN (INPUTS) ---
    with left_col:
        # This input section is unchanged from your last working version
        st.markdown("<h4 style='text-align: center;'>📄 Input Details</h4>", unsafe_allow_html=True)
        profile_tab1, profile_tab2 = st.tabs(["Upload PDF", "Paste Text"])
        with profile_tab1:
            uploaded_candidate_file = st.file_uploader("Upload Candidate Profile or Resume", type=["pdf", "txt"], key="candidate_uploader")
            with st.expander("ℹ️ How to get a LinkedIn Profile PDF"):
                st.write("1. Navigate to the LinkedIn profile you want to save.")
                st.write("2. Click the **'More'** button.")
                st.image("assets/moreImage.png")
                st.write("3. Select **'Save to PDF'** from the dropdown menu.")
        with profile_tab2:
            candidate_profile_text_input = st.text_area("Paste the candidate's full resume or profile text here", height=250, key="candidate_text", label_visibility="collapsed")
        
        jd_tab1, jd_tab2 = st.tabs(["Upload PDF", "Paste Text"])
        with jd_tab1:
            uploaded_job_file = st.file_uploader("Upload Job Description", type=["pdf", "txt"], key="job_uploader")
        with jd_tab2:
            job_description_text_input = st.text_area("Paste the full job description here", height=250, key="job_text", label_visibility="collapsed")
        
        recruiter_name = st.text_input("Your Name (Recruiter)", placeholder="Your Name")
        company_name = st.text_input("Company Name", placeholder="Your Company")
        role_title = st.text_input("Role Title", placeholder="e.g., Senior AI Engineer")


        generate_button = st.button("✨ Generate Messages", use_container_width=True, type="primary")

    # ---------- LOGIC & OUTPUT (RIGHT COLUMN) ----------
    with right_col:
        st.markdown("<h4 style='text-align: center;'>✍️ Generated Content</h4>", unsafe_allow_html=True)

        if 'output' not in st.session_state:
            st.session_state.output = None

        if 'loading' not in st.session_state:
            st.session_state.loading = False

        if generate_button:
            st.session_state.output = None
            candidate_profile, job_description = "", ""
            # Candidate profile extraction
            if uploaded_candidate_file:
                if uploaded_candidate_file.type == "application/pdf":
                    candidate_profile = extract_text_from_pdf(uploaded_candidate_file)
                elif uploaded_candidate_file.type == "text/plain":
                    candidate_profile = uploaded_candidate_file.read().decode("utf-8")
            elif candidate_profile_text_input:
                candidate_profile = candidate_profile_text_input
            # Job description extraction
            if uploaded_job_file:
                if uploaded_job_file.type == "application/pdf":
                    job_description = extract_text_from_pdf(uploaded_job_file)
                elif uploaded_job_file.type == "text/plain":
                    job_description = uploaded_job_file.read().decode("utf-8")
            elif job_description_text_input:
                job_description = job_description_text_input

            missing_fields = []
            if not candidate_profile or not job_description:
                missing_fields.append("candidate profile and job description")
            if not recruiter_name:
                missing_fields.append("recruiter name")
            if not company_name:
                missing_fields.append("company name")
            if not role_title:
                missing_fields.append("role title")

            if missing_fields:
                st.warning(f"Please provide: {', '.join(missing_fields)}.", icon="⚠️")
                st.session_state.output = None # Clear previous output on new attempt with missing info
                st.session_state.loading = False
            else:
                with st.spinner("Working its magic..."):
                    try:
                        user_prompt = f"""[CANDIDATE_PROFILE]{candidate_profile}[END_CANDIDATE_PROFILE][JOB_DESCRIPTION]{job_description}[END_JOB_DESCRIPTION][RECRUITER_NAME]{recruiter_name}[COMPANY_NAME]{company_name}[ROLE_TITLE]{role_title}"""
                        response = client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}])
                        raw_output = response.choices[0].message.content
                        st.session_state.output = parse_ai_output(raw_output)

                        # CRITICAL: If this was a free user, set the cookie and rerun
                        if not st.session_state.authentication_status:
                            # Get the current count again before incrementing
                            current_count = int(cookies.get('generation_count', 0))
                            new_count = current_count + 1
                            # Save the new count back to the cookie
                            cookies['generation_count'] = str(new_count)
                            st.rerun()

                    except Exception as e:
                        st.error(f"An error occurred: {e}", icon="🚨")
                        st.session_state.output = None
                    st.session_state.loading = False

        # Display logic that's always running
        info_tab, messages_tab, email_tab = st.tabs(["Candidate Info", "Short Messages", "Long Message"])
        
        if st.session_state.output:
            with info_tab:
                st.markdown(f"<h3 style='text-align: center; font-weight: bold;'>{st.session_state.output['name']}</h3>", unsafe_allow_html=True)
                formatted_points = st.session_state.output["key_points"].replace(":**", ":**\n")
                st.markdown(formatted_points)
            with messages_tab:
                # Your message display logic...
                for i, msg in enumerate(st.session_state.output["short_messages"]):
                    st.markdown(f"<div style='text-align: center; font-weight: bold;'>Option {i+1}</div>", unsafe_allow_html=True)
                    st.markdown("\n")
                    st.markdown(msg)
                    st.divider()
            with email_tab:
                # Your email display logic...
                st.markdown(st.session_state.output["long_message"])
        else:
            with info_tab:
                st.info("The candidate's summarized profile will appear here.")
            with messages_tab:
                st.info("Short message options will appear here.")
            with email_tab:
                st.info("A detailed email draft will appear here.")

# -----------------------------------------------------------------
# 5. MAIN ROUTER
# -----------------------------------------------------------------

# The login form must be at the top level of the script
name, authentication_status, username = authenticator.login('main')
st.session_state['authentication_status'] = authentication_status

if authentication_status:
    # --- USER IS LOGGED IN ---
    with st.sidebar:
        st.title(f"Welcome {name}!")
        authenticator.logout('Logout', 'main')
    run_main_app()

elif authentication_status == False:
    # --- FAILED LOGIN ---
    st.error('Username/password is incorrect')
    show_paywall()

elif authentication_status == None:
    # --- NO ONE IS LOGGED IN (NEW OR GATED VISITOR) ---
    # Get the current generation count from the cookie, default to 0 if not found
    generation_count = int(cookies.get('generation_count', 0))

    if generation_count > 3:
        show_paywall()
    else:
        # Display the remaining count for the user
        st.info(f"You have {3 - generation_count} free generations remaining.")
        run_main_app()
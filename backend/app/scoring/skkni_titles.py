"""Static English translations for the 27 SKKNI (AI subbidang Knowledge Based
System) unit competency titles ingested from SKKNI_2026-103.pdf. The source
PDF -- and therefore every unit_title Chroma metadata field -- is written in
Bahasa Indonesia; a fixed set of 27 units never changes, so translating once
here (and keying by the stable unit_code, not the Indonesian phrase) is far
more reliable than asking an LLM to translate on every render. Every surface
that displays a unit title (the frontend context panel, the consultation
chat, the poster, and the PDF report) reads it from UnitCoverageResult.unit_title
(app/scoring/gap_engine.py), which is translated once at analysis time via
english_unit_title() below -- so this is the single source of truth, not one
of several per-renderer translation layers.

Every unit's individual elements are translated the same way, below, keyed by
(unit_code, element_number). This isn't just display polish: text_evidence.py
asks the chat model to judge a student's resume/activity text against these
element titles, and a live check found the model returning an empty match set
for genuinely relevant evidence when handed the raw Indonesian titles, then
correctly identifying the match once given the English translation -- so an
untranslated element silently makes text-evidence matching a no-op for that
element, not just a display nicety.
"""

UNIT_TITLES_EN: dict[str, str] = {
    "K.62AIN00.001.2": "Determining Business Objectives for Artificial Intelligence Solutions",
    "K.62AIN00.002.2": "Determining Technical Objectives for Artificial Intelligence Solutions",
    "K.62AIN00.003.2": "Determining the Technical Architecture of Artificial Intelligence Solutions",
    "K.62AIN00.004.2": "Creating an Artificial Intelligence Solution Project Plan",
    "K.62AIN00.005.2": "Determining Technical Objectives for Artificial Intelligence Models",
    "K.62AIN00.006.2": "Designing Knowledge for Artificial Intelligence Solutions",
    "K.62AIN00.007.2": "Acquiring Knowledge for Artificial Intelligence Solutions",
    "K.62AIN00.008.2": "Representing Knowledge for Artificial Intelligence Solutions",
    "K.62AIN00.009.2": "Validating Knowledge for Artificial Intelligence Solutions",
    "K.62AIN00.010.2": "Determining Data Labeling Procedures",
    "K.62AIN00.011.2": "Analyzing Data for Artificial Intelligence Solutions",
    "K.62AIN00.012.2": "Filtering Data for Artificial Intelligence Solutions",
    "K.62AIN00.013.2": "Reconstructing Data",
    "K.62AIN00.014.1": "Determining the Development Strategy for Generative-Model-Based Artificial Intelligence Solutions",
    "K.62AIN00.015.1": "Developing Prompts for Generative Models",
    "K.62AIN00.016.1": "Adapting Generative Models",
    "K.62AIN00.017.1": "Injecting Knowledge into Generative Models",
    "K.62AIN00.018.1": "Evaluating Generative Model Output",
    "K.62AIN00.019.1": "Applying Fairness Principles to Artificial Intelligence Solutions",
    "K.62AIN00.020.1": "Applying Explainability Principles to Artificial Intelligence Solutions",
    "K.62AIN00.021.1": "Applying Reliability Principles to Artificial Intelligence Solutions",
    "K.62AIN00.022.1": "Ensuring Data Privacy Protection",
    "K.62AIN00.023.1": "Ensuring Accountability of Artificial Intelligence Solutions",
    "K.62AIN00.024.2": "Integrating Artificial Intelligence Solution Components",
    "K.62AIN00.025.2": "Installing Artificial Intelligence Solutions",
    "K.62AIN00.026.2": "Planning Artificial Intelligence Solution Maintenance",
    "K.62AIN00.027.2": "Maintaining Artificial Intelligence Solutions",
}


def english_unit_title(unit_code: str, fallback: str) -> str:
    """Falls back to whatever title was parsed from the PDF (Indonesian) only
    for a unit_code this table doesn't know about -- e.g. a future SKKNI
    revision -- so a missing translation degrades to the original text
    rather than an empty string."""
    return UNIT_TITLES_EN.get(unit_code, fallback)


ELEMENT_TITLES_EN: dict[tuple[str, str], str] = {
    ("K.62AIN00.001.2", "1"): "Identifying the business problems and objectives of the AI project",
    ("K.62AIN00.001.2", "2"): "Defining success criteria for the AI project's business objectives",
    ("K.62AIN00.002.2", "1"): "Determining the technical objectives of the AI Solution",
    ("K.62AIN00.002.2", "2"): "Determining success criteria for the AI Solution's technical objectives",
    ("K.62AIN00.003.2", "1"): "Identifying the technical scope of the AI Solution",
    ("K.62AIN00.003.2", "2"): "Developing the technical architecture components of the AI Solution",
    ("K.62AIN00.004.2", "1"): "Preparing a detailed execution plan for the AI Solution project",
    ("K.62AIN00.004.2", "2"): "Identifying risks and alternative execution approaches",
    ("K.62AIN00.004.2", "3"): "Identifying cost components and amounts",
    ("K.62AIN00.005.2", "1"): "Defining the technical objectives of the AI model",
    ("K.62AIN00.005.2", "2"): "Identifying success criteria for the AI model",
    ("K.62AIN00.006.2", "1"): "Determining the type of knowledge representation",
    ("K.62AIN00.006.2", "2"): "Designing the knowledge schema",
    ("K.62AIN00.007.2", "1"): "Designing the knowledge acquisition process",
    ("K.62AIN00.007.2", "2"): "Performing knowledge acquisition",
    ("K.62AIN00.008.2", "1"): "Determining tools for knowledge representation",
    ("K.62AIN00.008.2", "2"): "Building domain knowledge",
    ("K.62AIN00.008.2", "3"): "Building supplementary knowledge",
    ("K.62AIN00.009.2", "1"): "Determining verification of the knowledge structure",
    ("K.62AIN00.009.2", "2"): "Determining domain-based knowledge validation",
    ("K.62AIN00.009.2", "3"): "Updating knowledge based on verification and validation results",
    ("K.62AIN00.010.2", "1"): "Identifying requirements for a data-labeling procedure",
    ("K.62AIN00.010.2", "2"): "Building the data-labeling procedure",
    ("K.62AIN00.010.2", "3"): "Evaluating the execution of data labeling",
    ("K.62AIN00.011.2", "1"): "Preparing data for analysis",
    ("K.62AIN00.011.2", "2"): "Reviewing data types and relationships",
    ("K.62AIN00.011.2", "3"): "Reviewing data quality",
    ("K.62AIN00.011.2", "4"): "Preparing a data review report",
    ("K.62AIN00.012.2", "1"): "Determining criteria and techniques for data filtering",
    ("K.62AIN00.012.2", "2"): "Filtering data according to requirements",
    ("K.62AIN00.012.2", "3"): "Determining adjustments to data volume",
    ("K.62AIN00.013.2", "1"): "Analyzing feature engineering and data transformation techniques",
    ("K.62AIN00.013.2", "2"): "Building feature engineering and data transformation",
    ("K.62AIN00.013.2", "3"): "Documenting data reconstruction",
    ("K.62AIN00.014.1", "1"): "Determining the objective for using the generative model",
    ("K.62AIN00.014.1", "2"): "Determining the type of development approach",
    ("K.62AIN00.014.1", "3"): "Detailing the generative model's development components",
    ("K.62AIN00.015.1", "1"): "Determining the objective of prompt development",
    ("K.62AIN00.015.1", "2"): "Structuring a prompt for a specific need",
    ("K.62AIN00.015.1", "3"): "Validating the prompt's output",
    ("K.62AIN00.016.1", "1"): "Designing the Generative AI model's adaptation technique",
    ("K.62AIN00.016.1", "2"): "Preparing a dataset for Generative AI model adaptation",
    ("K.62AIN00.016.1", "3"): "Performing Generative AI model adaptation",
    ("K.62AIN00.016.1", "4"): "Validating the performance of the adapted Generative AI model",
    ("K.62AIN00.017.1", "1"): "Designing the knowledge-injection technique for the Generative AI model",
    ("K.62AIN00.017.1", "2"): "Preparing a corpus for the knowledge-injection model",
    ("K.62AIN00.017.1", "3"): "Building the knowledge-injection pipeline",
    ("K.62AIN00.017.1", "4"): "Implementing the knowledge-injection model into the AI application",
    ("K.62AIN00.017.1", "5"): "Validating the performance of the knowledge-injection model",
    ("K.62AIN00.018.1", "1"): "Identifying the evaluation context for the generative model's output",
    ("K.62AIN00.018.1", "2"): "Systematically evaluating the generative model's output",
    ("K.62AIN00.018.1", "3"): "Providing recommendations to improve the generative model's output",
    ("K.62AIN00.019.1", "1"): "Identifying fairness issues in the AI Solution",
    ("K.62AIN00.019.1", "2"): "Defining fairness evaluation indicators",
    ("K.62AIN00.019.1", "3"): "Applying fairness principles across the AI Solution lifecycle",
    ("K.62AIN00.020.1", "1"): "Identifying explainability requirements for the AI Solution",
    ("K.62AIN00.020.1", "2"): "Applying explainability techniques to the AI Solution",
    ("K.62AIN00.020.1", "3"): "Evaluating the quality of the AI Solution's explainability",
    ("K.62AIN00.020.1", "4"): "Recommending AI Solution improvements based on explainability results",
    ("K.62AIN00.021.1", "1"): "Identifying risks to the AI system's reliability",
    ("K.62AIN00.021.1", "2"): "Applying reliability evaluation techniques",
    ("K.62AIN00.021.1", "3"): "Recommending reliability improvements for the AI Solution",
    ("K.62AIN00.022.1", "1"): "Determining privacy-violation risks in the AI system",
    ("K.62AIN00.022.1", "2"): "Applying privacy-protection principles across the AI lifecycle",
    ("K.62AIN00.022.1", "3"): "Recommending improvements to data privacy protection",
    ("K.62AIN00.023.1", "1"): "Identifying the AI Solution's accountability problems and objectives",
    ("K.62AIN00.023.1", "2"): "Defining the AI Solution's accountability criteria",
    ("K.62AIN00.023.1", "3"): "Applying accountability across the AI Solution's development lifecycle",
    ("K.62AIN00.024.2", "1"): "Identifying the solution components to be integrated",
    ("K.62AIN00.024.2", "2"): "Combining the AI Solution's technical architecture components",
    ("K.62AIN00.024.2", "3"): "Internally testing the integrated system",
    ("K.62AIN00.025.2", "1"): "Preparing the deployment environment",
    ("K.62AIN00.025.2", "2"): "Deploying the AI Solution",
    ("K.62AIN00.025.2", "3"): "Performing post-deployment validation and testing",
    ("K.62AIN00.025.2", "4"): "Applying security safeguards to the AI Solution",
    ("K.62AIN00.025.2", "5"): "Preparing documentation and monitoring",
    ("K.62AIN00.026.2", "1"): "Preparing the AI Solution maintenance plan",
    ("K.62AIN00.026.2", "2"): "Drafting the AI Solution maintenance plan",
    ("K.62AIN00.027.2", "1"): "Preparing AI Solution maintenance based on the maintenance plan",
    ("K.62AIN00.027.2", "2"): "Performing AI Solution maintenance based on the maintenance plan",
}


def english_element_title(unit_code: str, element_number: str, fallback: str) -> str:
    """Same fallback contract as english_unit_title(): degrades to the
    Indonesian text parsed from the PDF for an (unit_code, element_number)
    pair this table doesn't know about, rather than an empty string."""
    return ELEMENT_TITLES_EN.get((unit_code, element_number), fallback)

/**
 * CareBridge — English dictionary. This file is the CONTRACT.
 *
 * `Translations` is derived from this object, so every other language is checked against
 * it by the compiler. Two rules for anyone editing this file:
 *
 *   1. Add a key here first, then add it to hi / te / pa. `tsc` will tell you which.
 *   2. Never put a patient-facing sentence anywhere but here. A literal string inside a
 *      component is a sentence that only English speakers will ever read.
 *
 * Product names and clinical identifiers — Grad-CAM, ICDR, EfficientNetV2-S, CORAL —
 * stay recognisable in every language. Their EXPLANATIONS are translated.
 */
export const en = {
  common: {
    appName: "CareBridge",
    appTagline: "Your screening, in your language",
    brand: "Diabetic Retinopathy Screening",
    language: "Language",
    yourCareLanguage: "Your care language",
    changeLanguage: "Change language",
    voiceGuidance: "Voice guidance",
    explanationLevel: "Explanation level",
    simple: "Simple",
    clinical: "Clinical",
    simpleHint: "Plain language for the person being screened",
    clinicalHint: "Full clinical detail, grades and evidence",
    on: "On",
    off: "Off",
    listen: "Listen",
    playing: "Playing…",
    stop: "Stop",
    close: "Close",
    back: "Back",
    next: "Next",
    done: "Done",
    showMore: "Show more",
    showLess: "Show less",
    loading: "Loading…",
    notAvailable: "Not available",
    disclaimer: "Screening triage aid — not a diagnostic device",
    curatedNote:
      "CareBridge uses translations written and reviewed by people. Nothing you upload is sent to a translation service.",
  },

  nav: {
    overview: "Overview",
    screen: "Screen an image",
    review: "Clinician review",
    evidence: "Evidence",
    reports: "Reports",
    howItWorks: "How it works",
    limitations: "Limitations",
    carebridge: "CareBridge",
    passport: "Passport",
    login: "Login",
    signup: "Create account",
    logout: "Logout",
  },

  onboarding: {
    eyebrow: "CareBridge",
    title: "Welcome to your eye screening",
    subtitle: "Choose how you would like to experience your results.",
    voiceNote: "Voice guidance available",
    changeLater: "You can change this at any time.",
    chooseAction: "Choose",
    selected: "Selected",
    startScreening: "Start screening",
    dismiss: "Not now",
    firstRunTitle: "Before we begin — which language do you read?",
    firstRunBody:
      "Your result, the explanation behind it and the follow-up advice will all be shown in the language you pick.",
  },

  journey: {
    title: "One choice, the whole journey",
    intro:
      "The language you pick is used by every patient-facing part of this service, and by the modules added to it later.",
    detect: "Detect",
    detectBody: "The image is checked for quality, then graded.",
    understand: "Understand",
    understandBody: "The result is explained in plain words.",
    communicate: "Communicate",
    communicateBody: "Read it, or have it read aloud to you.",
    guide: "Guide",
    guideBody: "Clear follow-up and lifestyle steps.",
    act: "Act",
    actBody: "A report you can take to a doctor.",
  },

  auth: {
    signInTitle: "Sign in",
    signInSub: "Enter your mobile number. We will send you a one-time code.",
    createTitle: "Create an account",
    createSub: "Screening needs a verified mobile number. There is no password.",
    mobileLabel: "Mobile number",
    otpPrompt: "Enter the code we sent you.",
    noPassword: "No password is ever stored for your account.",
    languageStays: "Changing your language does not sign you out.",
  },

  screen: {
    title: "Screen a retinal photograph",
    subtitle: "Upload one photograph of the back of the eye. Results take a few seconds.",
    upload: "Upload a fundus photograph",
    uploadHint: "Drag and drop, or tap to choose. Resized in your browser before upload.",
    analyzing: "Analysing…",
    analyzingHint: "Checking image quality, then grading. Please do not close this page.",
    patientRef: "Patient reference (optional)",
    asUploaded: "As uploaded",
    whatYouGetTitle: "What you get back",
    whatYouGet: [
      "A severity grade from 0 to 4, and whether a referral is needed",
      "A picture of the areas the system looked at",
      "An explanation you can read or listen to",
      "Clear next steps, and a one-page report to carry to a doctor",
      "Or a request to retake the photograph, if it cannot be read reliably",
    ],
  },

  quality: {
    failTitle: "The photograph is not clear enough",
    whyTitle: "Why?",
    whyBody:
      "The retinal photograph could not be read reliably, so no grade has been produced. Guessing from an unclear image would be worse than asking again.",
    whatToDoTitle: "What to do",
    whatToDoBody:
      "Please take the photograph again with better focus, steadier positioning and even lighting.",
    instructionTitle: "Specific instruction from the check",
    scoreLabel: "Image quality score",
    passTitle: "Image quality accepted",
    checksTitle: "Image quality gate",
    focus: "Focus",
    illumination: "Lighting",
    fieldOfView: "Field of view",
    passed: "Passed",
    failed: "Needs attention",
    noGradeNote: "No grade and no follow-up advice are shown for an unreadable photograph.",
    retake: "Retake the photograph",
  },

  result: {
    eyebrow: "Your screening result",
    title: "Your screening result",
    gradeWord: "Grade",
    gradeOf: "Grade {grade} of 4",
    labels: [
      "No diabetic retinopathy seen",
      "Very early changes",
      "Moderate changes",
      "Severe changes",
      "Advanced changes",
    ],
    clinicalLabels: [
      "No DR",
      "Mild NPDR",
      "Moderate NPDR",
      "Severe NPDR",
      "Proliferative DR",
    ],
    verdictRefer: "An eye doctor should see you",
    verdictReferBody: "The changes found are at or above the level that needs a specialist.",
    verdictClear: "No referral needed today",
    verdictClearBody: "Below the referral level. Continue routine re-screening.",
    whatItMeans: "What does this mean?",
    meaning: [
      "Today's photograph did not show signs of diabetes affecting the back of your eye. Keeping your blood sugar and blood pressure controlled is what keeps it that way.",
      "Very early changes were seen in the tiny blood vessels at the back of your eye. This is common and usually does not affect your sight now. Good control of blood sugar and blood pressure is the most useful thing you can do.",
      "Clear changes were seen in the blood vessels at the back of your eye. Your sight may still feel completely normal. This is not a loss of sight — it is the point at which an eye doctor should look at your eyes.",
      "Many changes were seen in the blood vessels at the back of your eye. Sight can still be normal at this stage. An eye specialist should examine you soon, because treatment works best before symptoms start.",
      "Advanced changes were seen, including fragile new blood vessels. This stage can affect sight, and it is treatable. Please see an eye specialist as quickly as you can.",
    ],
    clinicalDetails: "Clinical details",
    clinicalDetailsHint: "Grades, probabilities, lesion counts and the ICDR rule cross-check.",
    clinicalOpen: "Show clinical details",
    clinicalClose: "Hide clinical details",
    confidence: "Confidence",
    confidenceNote:
      "Confidence is how sure the system is about the grade it reported — not a probability that you have the disease.",
    calibrated: "calibrated",
    uncalibrated: "not calibrated",
    modelUnavailableTitle: "A grade could not be produced",
    modelUnavailableBody:
      "The photograph was clear enough, but the grading model did not run. The lesion evidence and the clinical-rule cross-check below are still valid.",
    scanRef: "Screening reference",
    speakIntro: "Listen to this explanation",
  },

  explainability: {
    title: "Why did the system say this?",
    gradCamTitle: "Grad-CAM — where the system looked",
    gradCamPlain:
      "The bright areas show the parts of your photograph the system paid most attention to while deciding. They are not, by themselves, a diagnosis.",
    gradCamTech:
      "Gradient-weighted class activation mapping over the final convolutional block of the EfficientNetV2-S backbone, for the referability output of the CORAL ordinal head.",
    lesionsTitle: "Marked findings",
    lesionsPlain:
      "The coloured marks show small spots and leaks found by a separate, rule-based image analysis — a second opinion that does not use the neural network.",
    unavailable: "The heatmap is not available for this photograph.",
    attentionTitle: "Attention summary",
    note: "Both views describe the same single photograph you uploaded.",
  },

  actions: {
    title: "What should I do now?",
    eyeTitle: "Eye follow-up",
    eyeBody: [
      "Have your eyes photographed again in about 12 months, or sooner if your vision changes.",
      "Have your eyes checked again in 6 to 12 months. Tell your doctor if your vision changes.",
      "Book an appointment with an eye doctor. Programme guidance is within about 3 months.",
      "See an eye specialist soon — programme guidance is within a few weeks.",
      "See an eye specialist urgently, within days. Do not wait for symptoms.",
    ],
    lifestyleTitle: "Lifestyle support",
    lifestyleBody: "Food, activity and blood-sugar habits that protect your eyes.",
    reportTitle: "Your report",
    reportBody: "A one-page summary you can show to a doctor.",
    download: "Download report (PDF)",
    urgentTag: "Do this first",
    generalTag: "Routine",
  },

  /**
   * CareBridge — WhatsApp report delivery.
   *
   * Delivery copy only. Not one string in this block states a clinical fact: the grade,
   * the referral and the explanation are already on the page above it, and the message
   * WhatsApp carries is composed by the backend from the same screening result.
   */
  whatsapp: {
    eyebrow: "Delivery",
    readyTitle: "Your screening report is ready",
    readyBody: "Your detailed CareBridge report has been generated successfully.",
    channelLabel: "WhatsApp delivery",
    verifiedNumberIntro: "Send this report to your verified WhatsApp number:",
    send: "Send report on WhatsApp",
    sending: "Sending report…",
    sentShort: "Report sent to WhatsApp",
    queuedShort: "WhatsApp message queued for delivery",
    failedShort: "Unable to send the report",
    retry: "Try again",
    explain: "Your PDF will be delivered to your registered WhatsApp number.",
    registeredNote: "We use the number you signed in with. You never have to type it again.",
    successTitle: "Report sent successfully",
    successBody: "Your screening report has been sent to:",
    successHint: "Open WhatsApp to view the PDF.",
    alsoDownload: "The report stays available here whether or not it is sent.",
    journeyScreen: "Screened",
    journeyUnderstand: "Explained",
    journeyReport: "Report ready",
    journeyDeliver: "On WhatsApp",
    errors: {
      notConfigured: "WhatsApp delivery is not configured.",
      notConfiguredHint: "The report is still available to download on this page.",
      trialLimited: "WhatsApp delivery is not available on this account.",
      notReachable: "This number has not joined WhatsApp messaging from us yet.",
      recipientNotAllowed: "This number is not on the WhatsApp test recipient list yet.",
      sessionClosed: "Send us a WhatsApp message first, then try again.",
      invalidRecipient: "Your registered number cannot receive WhatsApp messages.",
      optedOut: "This number has opted out of our WhatsApp messages.",
      rateLimited: "Too many messages at once. Try again in a moment.",
      mediaUnreachable: "The report could not be attached. Try again.",
      unreachable: "Could not reach the messaging service. Try again.",
      reportMissing: "This report is no longer available to send.",
      alreadySending: "This report is already being sent.",
      generic: "Unable to send the report on WhatsApp.",
    },
  },

  // ---------------------------------------------------------------- Eye Health Passport
  // The longitudinal journey: what has changed since last time, and when to come back.
  // Every sentence here talks about the SCREENING RESULT, never about the disease —
  // the same rule src/passport/comparison.py enforces on the backend.
  passport: {
    eyebrow: "Eye Health Passport",
    title: "Your Eye Health Passport",
    subtitle: "Every screening you have had, and what changed between them.",
    returnTitle: "Your previous screening is available",
    returnBody: "You were last screened on {date}. Upload a new photograph and we will compare it with that result.",
    returnLastGrade: "Last result: Grade {grade} of 4",
    returnCta: "See your passport",
    emptyTitle: "Your passport starts with your first screening",
    emptyBody: "Once you have been screened, every visit appears here so you and your doctor can see what has changed.",
    emptyCta: "Screen an image",
    screeningsCount: "{count} screenings recorded",
    oneScreening: "1 screening recorded",
    comparisonTitle: "Screening comparison",
    comparisonPrevious: "Previous",
    comparisonCurrent: "Current",
    comparisonChange: "Change",
    comparisonNoPreviousTitle: "This is your first screening",
    comparisonNoPreviousBody: "There is nothing to compare it with yet. Your next screening will be compared with this one.",
    comparisonUngradeableTitle: "This photograph could not be graded",
    comparisonUngradeableBody: "An ungraded photograph is not a result, so it is not compared with your previous screening. Please have the photograph taken again.",
    comparisonInterval: "{days} days between screenings",
    comparisonNotDiagnosis: "This compares two screening results. It is not a diagnosis, and it is not by itself evidence that the disease has changed. Only an eye-care professional can say that.",
    comparisonNewlyReferable: "This screening result is at or above the referral threshold, and the previous one was not. Clinical follow-up is recommended.",
    comparisonNoLongerReferable: "This screening result is below the referral threshold, and the previous one was above it. Keep your follow-up appointment.",
    comparisonQualityChanged: "Image quality was different between the two screenings.",
    comparisonClinicianReview: "Clinician review",
    categoryUnitOne: "ICDR category",
    categoryUnitMany: "ICDR categories",
    categorySame: "Same ICDR category",
    categoryHigher: "{n} {unit} higher",
    categoryLower: "{n} {unit} lower",
    timelineTitle: "ICDR grade timeline",
    timelineHint: "The ICDR grade is a category from 0 to 4, so the line holds each grade until your next screening changes it. Select a point to open that report.",
    timelineAxis: "ICDR grade",
    timelineUngradeable: "Photograph could not be graded",
    timelineTableTitle: "The same screenings as a list",
    timelinePointLabel: "Screening on {date}, grade {grade}",
    journeyTitle: "Your eye health journey",
    journeyHint: "Every screening, oldest first. It grows each time you are screened.",
    journeyReportAvailable: "Report available",
    journeyComparisonAvailable: "Comparison available",
    journeyFollowUpStep: "Follow-up reminder",
    journeyClinicalFollowUp: "Clinical follow-up recommended",
    journeyViewReport: "View report",
    followUpTitle: "Your next screening",
    followUpSuggested: "Suggested follow-up",
    followUpWindow: "Suggested {window}",
    followUpDue: "Target date: {date}",
    followUpDueNow: "This follow-up is due now.",
    followUpBasis: "Where this comes from",
    followUpClinicianSet: "Set by the reviewing clinician",
    followUpNote: "This is a guideline-informed suggestion, not a prescription. Your doctor's advice takes precedence over it.",
    followUpReminderPending: "Reminder not sent yet",
    followUpReminderSent: "Reminder sent to WhatsApp",
    followUpReminderFailed: "Reminder could not be sent",
    followUpSendReminder: "Send me this reminder on WhatsApp",
    followUpSending: "Sending reminder…",
    priorityRoutine: "Routine",
    prioritySoon: "Sooner than routine",
    priorityPrompt: "Prompt specialist assessment",
    priorityUrgent: "Urgent specialist assessment",
    sendTitle: "Send your comparison on WhatsApp",
    sendBody: "The comparison report shows both results side by side, with your timeline and your suggested follow-up.",
    sendButton: "Send comparison on WhatsApp",
    sendSending: "Sending comparison…",
    sendSentTitle: "Comparison sent successfully",
    sendSentBody: "Your comparison report has been sent to:",
    sendQueued: "WhatsApp message queued for delivery",
    sendFailed: "Unable to send the comparison",
    sendRetry: "Try again",
    sendNotAvailable: "There is no comparison for this screening yet.",
    download: "Download comparison report",
    downloading: "Preparing the report…",
    downloadFailed: "That comparison report is not available.",
    alsoDownload: "The comparison stays on this page and downloadable whether or not it is sent.",
    doctorTitle: "Patient screening history",
    doctorHint: "Every screening recorded for this patient, oldest first. Identified by internal account id only.",
    doctorNoAccessTitle: "Longitudinal history not available",
    doctorNoAccessBody: "Record a clinician review on this screening to open this patient's longitudinal record, or ask a programme administrator to assign it to you.",
    doctorSetFollowUp: "Set a clinician follow-up",
    doctorMonths: "Follow-up in (months)",
    doctorReason: "Reason (optional)",
    doctorSave: "Record follow-up",
    doctorSaved: "Follow-up recorded. The screening result is unchanged.",
    doctorPriority: "Priority",
  },

  nutrition: {
    title: "Food and lifestyle support",
    intro:
      "General guidance for people living with diabetes. It supports your treatment; it does not replace the medicines or diet your own doctor has given you.",
    personalizeTitle: "Make this fit your food",
    personalizeHint: "This choice only changes the examples shown. Nothing is saved.",
    dietMixed: "Mixed diet",
    dietVegetarian: "Vegetarian",
    dietMillet: "Millet-based",
    focusTitle: "Eat more of",
    focusMixed: [
      "Whole grains — hand-pounded rice, whole wheat roti",
      "Dals, beans and eggs at every main meal",
      "Fish or lean chicken instead of fried or red meat",
      "Green leafy vegetables, at least one portion a day",
      "Whole fruit such as guava, papaya or apple",
    ],
    focusVegetarian: [
      "Whole grains — hand-pounded rice, whole wheat roti",
      "Dals, rajma, chana and paneer at every main meal",
      "Curd or buttermilk without sugar",
      "Green leafy vegetables, at least one portion a day",
      "Whole fruit such as guava, papaya or apple",
    ],
    focusMillet: [
      "Ragi, jowar, bajra and foxtail millet in place of white rice",
      "Dals and groundnuts alongside the millet",
      "Green leafy vegetables, at least one portion a day",
      "Curd or buttermilk without sugar",
      "Whole fruit such as guava, papaya or apple",
    ],
    limitTitle: "Have less of",
    limitItems: [
      "Sugar, jaggery, sweets and sweetened drinks",
      "White rice and maida in large portions",
      "Deep-fried snacks and reused cooking oil",
      "Packaged biscuits, chips and namkeen",
      "Alcohol, and tobacco in every form",
    ],
    activityTitle: "Movement",
    activityBody:
      "About 30 minutes of brisk walking on most days. Split it into three short walks if that is easier.",
    controlTitle: "The two numbers that matter for your eyes",
    controlBody:
      "Blood sugar and blood pressure. Steady control over years protects the small vessels in the retina more than any single food does.",
    note: "Ask your doctor before making a large change to your diet, especially if you take insulin.",
    noGradeNote:
      "Food and lifestyle guidance is shown once a photograph has been graded.",
  },

  /**
   * Smart Care Finder — the step after the result.
   *
   * ACCESS copy only. Not one string in this block states a clinical fact, and none of
   * them describes a facility's quality. "Open now" and "Highly rated" are statements
   * about Google's listing data, shown only where Google actually supplied it, and the
   * badge note says so in the patient's own language.
   *
   * The `priority` list is chosen by the grade the page ALREADY has. It changes the
   * wording and the prominence of an access feature. It does not restate, soften or
   * sharpen the medical result, which is on the same page above it.
   */
  careFinder: {
    eyebrow: "Next step",
    continueTitle: "Continue your care",
    continueBody:
      "Your screening result is one step. Find nearby eye-care facilities for your next step.",
    title: "Smart Care Finder",
    lede: "Eye-care facilities near you, found on Google Places.",
    find: "Find nearby eye care",
    useMyLocation: "Use my location",
    gettingLocation: "Getting your location…",
    searching: "Finding nearby eye care…",
    resultsTitle: "Nearby eye care",
    within: "Within {km} km",
    foundCount: "{count} eye-care facilities found",
    privacyNote: "Your location is used only to find nearby eye-care facilities.",
    privacyDetail:
      "Only a map position is sent, and only when you ask for a search. Your name, your mobile number, your photograph and your result are never sent.",
    whyLabel: "Why am I seeing this?",
    whyBody:
      "Finding care is the step after a screening result. This list is not a recommendation: it is the eye-care services Google lists near the place you searched.",

    priority: {
      routine:
        "Routine eye care. It is worth knowing where to go before your next check-up is due.",
      followUp:
        "A follow-up is recommended. These are places near you where your eyes can be looked at.",
      clinical:
        "A clinical follow-up is recommended. Find an eye-care facility you can reach.",
      specialist:
        "A specialist evaluation is recommended. Find an eye-care facility you can reach.",
      review:
        "Your screening result needs clinician review. Find an eye-care facility you can reach.",
      unreadable:
        "No grade was produced from this photograph. You can still find an eye-care facility to have your eyes checked.",
    },

    view: {
      map: "Map",
      list: "List",
    },
    mapLabel: "Map of nearby eye-care facilities",
    mapUnavailable: "The map could not be loaded. The list has every facility.",
    yourLocation: "Your location",
    yourLocationHint: "Approximate position from your device.",
    markerLabel: "{name}, {distance}. Select to see details.",
    selectHint: "Select a facility to see its details and directions.",
    selected: "Selected",
    viewOnMap: "View on map",
    details: "Facility details",

    distanceKm: "{km} km away",
    distanceM: "{metres} m away",
    setupLabel: "Setup needed",
    distanceFromYou: "Distance from your location",
    distanceFromArea: "Distance from {area}",
    distanceLabel: "Distance",
    approx: "Approximate straight-line distance, not a travel distance.",
    openNow: "Open now",
    closed: "Closed",
    hoursUnknown: "Opening hours not published",
    rating: "{rating} out of 5",
    reviews: "{count} Google reviews",
    phone: "Phone",
    website: "Website",
    call: "Call",
    directions: "Get directions",
    directionsHint: "Opens Google Maps.",

    badges: {
      nearby: "Nearby",
      eyeFocused: "Eye-care focused",
      openNow: "Open now",
      highlyRated: "Highly rated",
    },
    badgeNote:
      "These labels describe how easy a place is to reach and what Google lists about it. They are not a judgement of medical quality.",

    manualTitle: "Search by city or area",
    manualHint: "Type the name of your town, city or district.",
    manualPlaceholder: "Town, city or district",
    manualSubmit: "Search this area",
    areaShown: "Showing eye care near {area}",
    changeArea: "Search a different area",

    emptyTitle: "No nearby eye-care facilities were found",
    emptyBody:
      "Nothing eye-related is listed within {km} km of the place you searched. That does not mean there is none in your region.",
    expand: "Search within {km} km",
    retry: "Try again",
    startOver: "Start again",

    attribution: "Facility information from Google",
    notEndorsement:
      "This is a list of nearby services, not a recommendation or an endorsement of any of them.",
    voiceIntro:
      "Here are nearby eye-care facilities. Select one to view details or get directions.",

    errors: {
      denied: "Location access was not granted.",
      deniedHint: "You can still search by typing your town or city.",
      timeout: "Getting your location took too long.",
      unavailable: "Your location could not be determined.",
      unsupported: "This browser cannot share a location.",
      notSetUp:
        "Nearby eye-care search has not been set up on this service yet.",
      notSetUpHint:
        "Your screening result and your report are complete and unaffected.",
      notConfigured: "Nearby eye-care search is not available right now.",
      notConfiguredHint: "Your result and your report are unaffected.",
      quota: "The nearby-care search is busy. Try again shortly.",
      network:
        "Could not reach the nearby-care service. Check the connection and try again.",
      areaNotFound: "That place could not be found. Try a nearby town or district.",
      rateLimited: "Too many searches. Try again in a little while.",
      generic: "Nearby eye-care search did not work. Try again.",
    },
  },

  sharing: {
    eyebrow: "Your record",
    title: "Who can see my screening history?",
    intro:
      "Nobody, until you say so. A doctor can only open your timeline, your reports and your follow-up plan after you have given them a code — and you can take that back at any time.",
    whoHasAccess: "Doctors with access",
    nobody: "No one has access to your screening history right now.",
    unnamedDoctor: "Verified doctor",
    sharedOn: "Shared on",
    revoke: "Remove access",
    giveAccess: "Give a doctor access",
    howItWorks:
      "Create a code and read it out to your doctor. It works once, and only for a short time.",
    createCode: "Create a sharing code",
    codeExpires: "This code stops working in about {minutes}.",
    codeOnce: "It is shown only once. If you lose it, create another.",
    unusedCodes: "Unused codes: {count}. Tap one to cancel it.",
    cancelCode: "Cancel code",
    why:
      "Removing access takes effect immediately. The doctor keeps any notes they already wrote, but can no longer open your record.",
    doctorAdd: "Add a patient",
    doctorAddHint: "Enter the sharing code the patient gave you.",
    doctorCodeLabel: "Sharing code",
    doctorAdded: "This patient's history is now available to you.",
    doctorNoPatients:
      "No patients have shared their record with you yet. Ask a patient to create a sharing code from their Eye Health Passport.",
  },
  why: {
    label: "Why am I seeing this?",
    body:
      "This information is based on your retinal screening result and is intended to help you understand that result. It does not replace evaluation by a qualified clinician.",
  },

  future: {
    title: "Built to carry the next module too",
    intro:
      "Anything added to this service later uses the same language, the same voice guidance and the same simple-or-clinical choice. A new feature adds its words to CareBridge; it does not build a language system of its own.",
    comingSoon: "Planned",
    telemedicine: "Teleconsultation",
    telemedicineBody: "Speak to a doctor in the language you chose here.",
    appointments: "Appointments",
    appointmentsBody: "Book and remember your eye check-ups.",
    education: "Patient education",
    educationBody: "Short explanations about diabetes and the eye.",
    reminders: "Follow-up reminders",
    remindersBody: "A message when your next screening is due.",
    medication: "Medicine information",
    medicationBody: "What your medicines do, in plain words.",
  },

  errors: {
    generic: "Something went wrong. Please try again.",
    network: "Could not reach the screening service. Check the connection and try again.",
    unreadable: "That file could not be read as an image.",
    empty: "Nothing to show yet.",
    voiceUnsupported: "This device cannot read text aloud.",
    voiceNoLanguage: "No {language} voice is installed on this device. The text is still here to read.",
  },

  a11y: {
    openLanguageMenu: "Open language and accessibility settings",
    languageMenu: "Language and accessibility settings",
    chooseLanguage: "Choose your care language",
    currentLanguage: "Current language: {language}",
    explanationLevelGroup: "Choose how much detail to show",
    speak: "Read this explanation aloud",
    stopSpeaking: "Stop reading aloud",
    voiceToggle: "Turn voice guidance on or off",
  },

  coverage: {
    title: "Translation coverage",
    intro: "Every key in the English dictionary, checked against each language.",
    languageColumn: "Language",
    keysColumn: "Keys",
    completeColumn: "Complete",
    missingTitle: "Missing keys",
    allComplete: "All languages complete.",
    devOnly: "Development tool — not shown in the production build.",
  },
};

/** The shape every language must satisfy. Derived, never hand-written. */
export type Translations = typeof en;

export default en;

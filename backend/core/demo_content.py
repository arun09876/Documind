"""Original sample documents for the demo account (fictional; written for DocuMind).

Each document is a list of pages; each page is a list of (heading, paragraph)
pairs. One entry in the outer list becomes exactly one PDF page, so page
citations in the demo are predictable.
"""

HANDBOOK_TITLE = "Northwind Labs Employee Handbook 2026"
HANDBOOK = [
    [
        ("Welcome to Northwind Labs",
         "This handbook explains how we work, what you can expect from us, and what we expect from you. It applies to all "
         "full-time and part-time employees of Northwind Labs in every office. Contractors should follow the separate "
         "Contractor Guide. If anything here conflicts with your employment contract or local law, the contract or the law "
         "takes precedence. The People Operations team owns this handbook and reviews it every January."),
        ("Our values",
         "We build carefully, we say what we think, and we leave things better than we found them. In practice that means "
         "writing things down, asking for help early, and disagreeing openly before a decision is made and committing "
         "fully once it is. We care more about outcomes than hours, and we trust people to manage their own time."),
        ("Who to contact",
         "Questions about pay, benefits or leave go to People Operations at people@northwind.example. IT and security "
         "questions go to the help desk. Anything you would rather raise confidentially can be sent to the Ethics Line, "
         "which is run by an independent provider and does not share your identity without your consent."),
    ],
    [
        ("Working hours",
         "Our core collaboration hours are 11:00 to 16:00 in your local office time zone. Outside those hours you may "
         "arrange your day as you like, provided you work your contracted hours, which are 40 hours per week for full-time "
         "staff. Meetings should not be scheduled outside core hours without the attendees' agreement."),
        ("Remote and hybrid work",
         "Northwind Labs is a hybrid company. Employees are expected in the office on Tuesdays and Thursdays, which are our "
         "anchor days. On other days you may work from home or from any location in the country of your employment "
         "contract. Working from another country requires written approval from People Operations and is limited to a "
         "maximum of 30 days in any 12-month period, because of tax and immigration rules."),
        ("Home office stipend",
         "New employees receive a one-time home office stipend of $500 to buy a desk, chair or other equipment. After that, "
         "a monthly internet allowance of $40 is paid with your salary. Receipts are required for the one-time stipend but "
         "not for the monthly allowance."),
    ],
    [
        ("Annual leave",
         "Full-time employees receive 24 days of paid annual leave per calendar year, in addition to public holidays. "
         "Part-time employees receive a pro-rated amount. Up to 5 unused days can be carried over into the next year; "
         "carried-over days must be used by March 31, after which they expire. Leave should be requested in the HR portal "
         "at least two weeks in advance for absences longer than three days."),
        ("Sick leave",
         "You are entitled to 12 days of paid sick leave per year. For absences longer than three consecutive working days, "
         "a doctor's note is required. Sick leave does not carry over and cannot be exchanged for pay. If you are unwell, "
         "tell your manager as early as possible on the first day; you do not need to share your diagnosis."),
        ("Parental leave",
         "Primary caregivers receive 26 weeks of fully paid parental leave, and secondary caregivers receive 6 weeks of "
         "fully paid leave. Parental leave can be taken any time within the first 12 months after a birth or adoption and "
         "may be split into up to three blocks. Employees returning from parental leave may work a reduced 4-day week at "
         "full pay for their first 4 weeks back."),
    ],
    [
        ("Business travel",
         "Book travel through the company travel portal so it is covered by our travel insurance. Economy class is standard "
         "for all flights; premium economy is allowed for flights longer than 6 hours. Hotels should be booked within the "
         "city rate caps shown in the portal. Travel must be approved by your manager before you book."),
        ("Meals and daily allowance",
         "When travelling for work you may claim up to $60 per day for meals, including tips. Alcohol is not reimbursable "
         "except at approved client events. The daily limit applies per person; when you pay for a group meal, list the "
         "attendees on the claim so the limit can be applied to each of them."),
        ("Submitting expenses",
         "Submit expense claims in the finance app within 30 days of the expense, with an itemised receipt for any item over "
         "$25. Claims are reviewed by your manager and then by Finance, and approved claims are reimbursed within 5 business "
         "days with your next payment run. Claims submitted more than 90 days after the expense will not be reimbursed."),
    ],
    [
        ("Equipment",
         "Every employee receives a company laptop, which is refreshed every 3 years, and a phone allowance of $30 per month "
         "if you use a personal phone for work. Company equipment remains the property of Northwind Labs and must be returned "
         "within 5 working days of your last day of employment."),
        ("Information security",
         "Two-factor authentication is mandatory for every company account, and passwords must be at least 14 characters. "
         "Customer data may only be stored in approved systems; never copy it to personal devices or unapproved cloud tools. "
         "Lock your screen whenever you step away, and do not share credentials with anyone, including colleagues."),
        ("Reporting incidents",
         "Report any suspected security incident, such as a lost laptop, a phishing email you clicked, or data sent to the "
         "wrong person, to the security team within 24 hours, even if you are not sure it is serious. Early reports are "
         "never punished; hiding an incident is a disciplinary matter."),
    ],
    [
        ("Performance reviews",
         "Performance reviews take place twice a year, in April and October. Each review combines a self-assessment, "
         "feedback from at least two peers, and a conversation with your manager. Compensation changes are decided once a "
         "year, in the April cycle, and take effect from May 1."),
        ("Learning and development",
         "Each employee has an annual learning budget of $1,200 for courses, books, certifications and conferences. Up to "
         "3 days per year of paid study leave can be taken for exams or conferences. Unused learning budget does not carry "
         "over. Requests over $500 need your manager's approval before you spend the money."),
        ("Leaving Northwind Labs",
         "The notice period is one month for employees in their first year and two months after that. Your manager will "
         "arrange a handover plan, and People Operations will schedule an exit interview. Remaining annual leave is paid out "
         "with your final salary."),
    ],
]

GUIDE_TITLE = "A Field Guide to Vector Search"
GUIDE = [
    [
        ("What an embedding is",
         "An embedding is a list of numbers that represents the meaning of a piece of text. Models are trained so that "
         "texts with similar meanings end up close together in this vector space, even when they share no words: "
         "\"time off for a new baby\" lands near \"parental leave\". Typical sentence-embedding models produce vectors "
         "with 384 to 1,536 dimensions. Smaller models such as BGE-small (384 dimensions) run comfortably on a CPU."),
        ("Measuring similarity",
         "The most common measure is cosine similarity: the cosine of the angle between two vectors, from -1 to 1. If "
         "vectors are normalised to unit length first, cosine similarity equals the dot product, which is cheaper to "
         "compute. Euclidean distance is an alternative; on normalised vectors it produces the same ranking as cosine "
         "similarity."),
    ],
    [
        ("Exact versus approximate search",
         "Exact (brute-force) search compares the query with every stored vector. It is perfectly accurate and fast "
         "enough for tens of thousands of vectors, especially as a single matrix multiplication. Beyond a few million "
         "vectors, approximate nearest neighbour (ANN) indexes trade a little recall for large speed-ups."),
        ("HNSW",
         "HNSW (Hierarchical Navigable Small World) builds a layered graph in which each vector links to its near "
         "neighbours. A search starts in the sparse top layer and greedily moves closer to the query, descending layer by "
         "layer. HNSW offers excellent recall and low latency, at the cost of higher memory use and slower index builds. "
         "Its main tuning knobs are M (links per node) and ef_search (how widely each query explores)."),
        ("IVF",
         "IVF (inverted file) indexes cluster the vectors, typically with k-means, and search only the few clusters "
         "nearest to the query. The nprobe parameter controls how many clusters are visited: higher values improve recall "
         "but slow queries down. IVF uses less memory than HNSW and builds faster, and it is often combined with product "
         "quantisation (IVF-PQ) to compress vectors for very large collections."),
    ],
    [
        ("Chunking documents",
         "Long documents are split into chunks before embedding, because a single vector cannot represent a whole book "
         "well and because answers need precise passages. Chunks of roughly 500 to 1,000 characters work well for most "
         "prose. Splitting on sentence boundaries keeps chunks readable, and overlapping neighbouring chunks by one or two "
         "sentences means a fact that straddles a boundary is not lost."),
        ("Keeping provenance",
         "Every chunk should remember where it came from: the document and the page numbers it spans. This metadata is "
         "what allows an answer to cite its source, so a reader can open the original page and check the claim. Without "
         "provenance, retrieval-augmented generation cannot be verified."),
    ],
    [
        ("Why hybrid search",
         "Embeddings capture meaning but blur exact tokens: product codes, error numbers and rare names often match "
         "poorly. Keyword ranking with BM25 is the opposite: precise on exact terms, blind to paraphrase. Hybrid search "
         "runs both and merges the results, which is consistently more robust than either alone."),
        ("Reciprocal rank fusion",
         "Reciprocal rank fusion (RRF) merges ranked lists without needing their scores to be comparable. Each document "
         "receives 1 / (k + rank) from every list it appears in, and the contributions are summed. The constant k is "
         "usually 60, which stops a single first-place ranking from dominating. RRF is simple, needs no training, and "
         "performs well in practice."),
    ],
    [
        ("Evaluating retrieval",
         "Measure retrieval separately from generation. Recall@k asks whether the passage containing the answer appears "
         "in the top k results; mean reciprocal rank (MRR) rewards putting it near the top. Build a small test set of "
         "questions with known source passages, and re-run it whenever you change the chunk size, the embedding model or "
         "the fusion settings."),
        ("Common failure modes",
         "Most bad answers trace back to retrieval, not to the language model: chunks that are too large dilute the "
         "signal, chunks that are too small lose context, and scanned PDFs without a text layer produce nothing to "
         "search. When the right passage is not retrieved, a well-instructed model should say it cannot find the answer "
         "rather than guess."),
    ],
]

SUGGESTED_QUESTIONS = [
    "How many weeks of parental leave do primary caregivers get?",
    "What's the daily meal allowance when travelling?",
    "How does HNSW compare to IVF?",
    "Why combine BM25 with vector search?",
]

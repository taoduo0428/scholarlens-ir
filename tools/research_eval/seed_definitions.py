"""Reviewed source selectors, research prompts, slots and review criteria; no human labels."""

# Row IDs refer to the immutable LFS object. Sentence numbers select a source passage
# in a paper abstract. Each task's anchors are independently located in legacy chunks.
GROUPS = [
    (
        "recommendation",
        "train",
        (995, 1872),
        [
            (
                "Which interaction does AARM add when product and user review aspects are sparse?",
                [(0, 6)],
                "mechanism",
                "Identify synonymous and similar aspect interactions.",
            ),
            (
                "Compare how AARM and CARCA use attention when modeling user preferences.",
                [(0, 7), (1, 3)],
                "attention_A,attention_B",
                "Distinguish product-dependent aspect attention from profile-to-item cross-attention.",
            ),
            (
                "Trace the CARCA next-item scoring mechanism to the historical profile items it can exploit.",
                [(1, 3), (1, 4)],
                "scoring,consequence",
                "Cite both the scoring contrast and the role of older profile items.",
            ),
            (
                "What dataset count and ranking metrics accompany the reported CARCA improvements?",
                [(1, 5)],
                "datasets,metrics",
                "Preserve the scope of the up-to improvement and metric names.",
            ),
            (
                "Do the abstracts establish a head-to-head superiority claim for AARM and CARCA on identical candidates?",
                [(0, 8), (1, 5)],
                "protocol,gap",
                "Separate top-N/next-item and avoid ranking without a matched experiment.",
            ),
            (
                "Give the CARCA authors' live serving costs in November 2026 from these abstracts.",
                [],
                "missing_cost",
                "Report the cost as unavailable in this bounded source scope.",
            ),
        ],
    ),
    (
        "language-models",
        "train",
        (792, 2076),
        [
            (
                "Which DSL shared task and track used a character model to distinguish similar languages?",
                [(0, 0), (0, 1)],
                "task,track",
                "Identify year, shared task and closed subtask.",
            ),
            (
                "Compare access to model internals required for context probing with the DSL classification setup.",
                [(1, 2), (0, 2)],
                "probe_access,architecture",
                "Keep black-box explanation and supervised classification distinct.",
            ),
            (
                "Explain how available context length creates importance scores and what access the probing method needs.",
                [(1, 1), (1, 2)],
                "operation,requirement",
                "Link prediction changes to token probabilities.",
            ),
            (
                "How did the character CLSTM and n-gram systems score in the 2016 DSL evaluation?",
                [(0, 2), (0, 4)],
                "clstm_accuracy,ngram_accuracy",
                "Match both accuracy values to the architectures and track.",
            ),
            (
                "Can context-probing results be ranked directly against closed-set DSL classification accuracy?",
                [(1, 3), (0, 4)],
                "outcomes,protocol",
                "Compare the evaluation aims and withhold cross-task ranking.",
            ),
            (
                "Name the individual test-set participants' email addresses from the DSL abstract.",
                [],
                "out_of_scope",
                "Decline the request for absent private information.",
            ),
        ],
    ),
    (
        "machine-translation",
        "train",
        (846, 1866),
        [
            (
                "What error taxonomy did the English-to-Croatian MT evaluation use?",
                [(0, 1)],
                "taxonomy",
                "Name MQM and how significance was assessed.",
            ),
            (
                "Contrast human evaluation in Croatian translation and prescription simplification.",
                [(0, 4), (1, 5)],
                "mt_raters,pharm_raters",
                "Separate annotated error types and pharmacist usability judgments.",
            ),
            (
                "Link the Croatian MT system paradigms to the best-versus-worst error reduction.",
                [(0, 2), (0, 5)],
                "paradigms,result",
                "Identify both reference systems and error reduction.",
            ),
            (
                "Which BLEU score and relative improvement did PharmMT report, and against what baseline?",
                [(1, 4)],
                "metric,baseline",
                "Keep BLEU and relative improvement separate.",
            ),
            (
                "Can one compare Croatian MQM error reduction directly with PharmMT BLEU improvement?",
                [(0, 5), (1, 4)],
                "units,task",
                "Identify different metrics, corpora and baselines; withhold ranking.",
            ),
            (
                "Provide the individual prescription records or patient identifiers used by PharmMT.",
                [],
                "restricted_records",
                "Only the aggregate source description is in scope.",
            ),
        ],
    ),
    (
        "summarization",
        "train",
        (1551, 1793),
        [
            (
                "Which unsupervised summarization approach ranks extractive sentences with transformer attention?",
                [(0, 2), (0, 4)],
                "model,scoring",
                "State the relationship between pretraining and sentence scores.",
            ),
            (
                "How does the document summarization setup differ from the TWEETSUMM customer-service setting?",
                [(0, 0), (1, 4)],
                "document,dialog",
                "Contrast unlabeled training and extractive/abstractive dialog summaries.",
            ),
            (
                "Trace the training material for the hierarchical summarizer to its benchmarks.",
                [(0, 3), (0, 5)],
                "pretraining,evaluation",
                "Connect unlabeled documents to the two named news datasets.",
            ),
            (
                "How many human-annotated summaries are described for TWEETSUMM, and of what types?",
                [(1, 3), (1, 4)],
                "count,types",
                "Keep the approximate qualifier and both summary types.",
            ),
            (
                "Do the papers demonstrate identical performance on news and customer-care dialogs?",
                [(0, 5), (1, 4)],
                "datasets,comparability",
                "Compare source domains and avoid claiming shared benchmark outcomes.",
            ),
            (
                "What exact per-agent salary savings did TWEETSUMM measure after deployment?",
                [],
                "salary",
                "Report no such figure in the scoped abstracts.",
            ),
        ],
    ),
    (
        "graph-learning",
        "dev",
        (1556, 1701),
        [
            (
                "Which operation incorporates symbolic domain knowledge into graph neural networks?",
                [(0, 4)],
                "operation",
                "Identify vertex-enrichment.",
            ),
            (
                "Compare vertex-enrichment and path reweighting as ways to modify GNNs.",
                [(0, 4), (1, 3)],
                "vertex,path",
                "Distinguish symbolic domain information from task-specific path weights.",
            ),
            (
                "Trace the vertex-enrichment evaluation from its scale to the authors' conclusion.",
                [(0, 5), (0, 6)],
                "scale,conclusion",
                "Keep the conclusion tied to the examined variants.",
            ),
            (
                "How many dataset and architecture variants were used to examine vertex enrichment?",
                [(0, 5)],
                "datasets,variants",
                "Preserve 'over' when giving the dataset count.",
            ),
            (
                "Can empirical results from vertex-enrichment and CustomGNN be ranked on one common leaderboard?",
                [(0, 5), (1, 6)],
                "protocol,scope",
                "Require a matched dataset/metric split before claiming ranking.",
            ),
            (
                "Which on-device battery current did CustomGNN draw during commercial deployment?",
                [],
                "missing_measurement",
                "State the measurement is outside the selected abstracts.",
            ),
        ],
    ),
    (
        "information-retrieval",
        "holdout",
        (2135, 2581),
        [
            (
                "Which measurement theory underpins the intrinsic framework of IR evaluation?",
                [(0, 2)],
                "theory",
                "Name representational measurement theory.",
            ),
            (
                "Contrast the object of study in intrinsic IR measures and the Airbnb location retrieval system.",
                [(0, 3), (1, 4)],
                "measurement,geography",
                "Separate measure properties and geographical candidate selection.",
            ),
            (
                "How does Airbnb place location retrieval in the search pipeline and define its output?",
                [(1, 3), (1, 4)],
                "pipeline,output",
                "Relate upstream-of-ranking to the map area for listings.",
            ),
            (
                "How many major categories of retrieval measures does the intrinsic framework distinguish?",
                [(0, 5)],
                "category_count",
                "Give the number, with the basis for classification.",
            ),
            (
                "Can the IR-measure taxonomy and the Airbnb system be ranked by a common observed nDCG gain?",
                [(0, 5), (1, 7)],
                "metrics,comparability",
                "Distinguish classification of measures from evaluating a deployed retrieval method.",
            ),
            (
                "What host-level current revenue numbers follow from the Airbnb location retrieval abstract?",
                [],
                "unavailable",
                "Keep individual current revenue out of the abstract-scoped answer.",
            ),
        ],
    ),
]

#1
I want to ask openclaw to build a local knowledge base. The source is from my literature stack, which is managed by mendeley. I have taken note in mendeley and the source pdf is organized based on year and publication name, and the files names are the name of the paper. Can you suggest an approach to realize that, involving coding or just use skills or MCP?

#2
A workable pattern is to treat Mendeley as the “system of record” (PDFs + citation metadata + your notes), then build a separate local index that OpenClaw can query. You can do this with almost no custom code (export + ingest), or you can make it robust with a small ingestion script plus an MCP server.

Option A: low-code (export from Mendeley → ingest a folder tree)

Keep your existing year/journal folder structure and paper-title filenames as the canonical storage. That is already a good “human index”.

Export citation metadata from Mendeley Reference Manager (BibTeX / RIS / EndNote XML). Mendeley explicitly supports “Export All” for these formats.

For annotations/notes: if you are using Mendeley Desktop (legacy) or any workflow that supports “Export PDF with annotations”, export annotated PDFs (either “PDF contents with notes/highlights” or “just the notes”) into a parallel folder (same relative paths).

Point OpenClaw’s local-file tooling at the root folder containing PDFs (and optionally the exported BibTeX/RIS). Then use (a) full-text extraction + chunking, (b) embeddings + vector search, (c) metadata filters (year/journal) derived from your folder structure and/or BibTeX fields.

This works well if your primary goal is “semantic search + cite the source PDF path + open it quickly”, and you can accept that Mendeley notes may need to be embedded into the PDFs (via “export with annotations”) rather than being synchronized as structured data.

Option B: “proper” local knowledge base (small ingestion script + MCP tools)
Here you build a local KB service that OpenClaw queries via MCP. The service owns indexing, deduplication, and metadata; OpenClaw just calls “search/get/open” tools.

Extract structured metadata: export BibTeX from Mendeley (same as Option A) and parse it to get stable keys (DOI if present; otherwise title+year+journal). Keep a mapping table: key → PDF absolute path → your folder-derived tags (year, venue).

Extract text for retrieval: for each PDF, run local text extraction (PyMuPDF/pdfminer). Chunk by section/paragraph, store chunks with fields like {key, chunk_id, text, page_range, year, venue, title, authors, doi, filepath}.

Capture your notes/highlights in a machine-usable way:

If your workflow can export “PDF with annotations”, ingest the exported annotated PDF so the note text is inside the document stream.

If you need the notes/highlights as separate structured objects, use the Mendeley API “annotations” resources to pull them and store them alongside the paper key (then index them too).

Serve the KB as an MCP server with a small tool surface such as: search_docs(query, filters), get_doc_metadata(key), get_doc_chunks(key), get_chunk(key, chunk_id), open_pdf(filepath), and (optional) add/update for incremental refresh. (A typical MCP KB exposes exactly these “search/get/list” patterns.)

Configure OpenClaw to use that MCP server as a tool provider, and keep OpenClaw’s direct filesystem permissions narrow (only the library root + the KB database directory). This matters because OpenClaw setups have had real-world footguns around overly broad filesystem access in default configurations.

Why MCP is the clean boundary here: you avoid teaching OpenClaw how to parse PDFs, BibTeX, and Mendeley edge cases. You give it a stable “knowledge API” instead (search + fetch + open). It also makes it easy to swap the backend (SQLite+FTS, Chroma/Qdrant, Elasticsearch) without reworking the agent prompts.

Practical details that make this reliable with your folder scheme
Use your directory layout as first-class metadata. Year and publication name from the path are fast filters and often more trustworthy than whatever was embedded in PDFs. Then enrich from BibTeX (title/authors/DOI). When a DOI exists, use it as the primary key; otherwise hash(normalized_title + year + first_author). Store the original PDF path and never rename automatically unless you intentionally run a “curation pass”.

If you tell me what Mendeley client you are actually using (Mendeley Reference Manager vs legacy Mendeley Desktop) and whether you require notes/highlights as separate searchable text (not just embedded into exported annotated PDFs), I can give you a concrete implementation sketch: either (1) a minimal Python ingestion + SQLite FTS + embeddings, or (2) an MCP server skeleton with the exact tool schema OpenClaw should call.

#3
I am using legacy Mendeley Desktop and I will need notes/highlights as separate searchable text

#4
If you need Mendeley Desktop notes/highlights as separate searchable text, the cleanest architecture is “export annotations → generate per-paper note files → index PDFs + note files together,” and then expose a small search API (via MCP) that OpenClaw can call.

The key constraint is that Mendeley Desktop stores annotations in its local database rather than writing them into the PDF, so you cannot reliably recover them just by re-parsing PDFs. Tools that export annotations either (a) use Mendeley’s own “Export PDF with Annotations” UI (manual per paper), or (b) read the local database and generate note text in bulk. Mendeley’s own blog describes the manual export route (File → Export PDF with Annotations, with an option to export “just the notes”).

A practical approach that matches your folder conventions

Maintain your canonical PDF library exactly as you described: root/year/publication/paper-title.pdf. Do not rename anything during ingestion; treat the filesystem path as ground truth for year and venue filters.

Bulk-export annotations to text/markdown, one file per paper, using a database-based exporter. The most widely used open-source option in the Mendeley Desktop ecosystem is “Menotexport,” which explicitly extracts highlights/sticky notes/general notes from the Mendeley database and can write them as plain text formatted with Markdown, while preserving the Mendeley folder structure.
Two important caveats from that project: (i) some Mendeley Desktop versions introduced database encryption (Menotexport documents this), so you may need a compatible Mendeley version or a decrypt workaround; (ii) the upstream tool was written for Python 2.7, so you likely run it inside a container/conda env pinned to Py2 (or use a maintained fork if you find one).

Put exported notes next to the PDFs in a predictable way. For example, keep your PDFs unchanged, and write notes as paper-title.mendeley.md in a sibling directory, or as paper-title.md under a parallel tree. Example:

/LitRoot/2021/Nature/Some Paper.pdf
/LitRoot_notes/2021/Nature/Some Paper.mendeley.md

Inside each markdown note, prepend a small metadata header (YAML front matter) that includes at least: title, year, publication, DOI (if present), and the absolute path to the PDF. This makes retrieval deterministic even if two papers share similar titles.

Index both corpora (PDF full text + markdown notes) into one retrieval store. In practice: chunk PDFs by page/section; chunk note files by annotation blocks. Store fields like {doc_key, source_type: pdf|note, text, page, highlight_color, created_time, year, venue, title, doi, pdf_path}. The point is that “note” chunks are first-class search targets, and PDF chunks remain available for grounding/quoting.

How this plugs into OpenClaw

If OpenClaw can already do local file indexing, you can often skip MCP and simply point it at both the PDF root and the notes root, with a rule that it prefers “note” hits for summarization and uses “pdf” hits for quoting with page refs. This works best if OpenClaw supports metadata filters; if it doesn’t, folder-derived filters still work by embedding year/venue into the note text header.

If you want it robust and controllable, use MCP and give OpenClaw only a few tools, so it never has to understand Mendeley internals:

Tool surface (minimal, sufficient):

kb.search(query, filters={year, venue, source_type}, k=20) → returns hits with {doc_key, source_type, snippet, score, pdf_path, note_path, page_range}

kb.get_note(doc_key) → returns the markdown note (or relevant sections)

kb.get_pdf_chunks(doc_key, page_range) → returns text chunks + page numbers

kb.open_pdf(pdf_path) (optional) → just returns the path for your local viewer integration

The MCP server itself is just a thin wrapper over your index (SQLite FTS5, Qdrant/Chroma, or even ripgrep+BM25). OpenClaw stays “stateless” and queries the KB like an external knowledge service.

Concrete “day-1” implementation path

Start with Menotexport to get notes out in bulk, because it already encodes years of Mendeley-specific quirks (annotations in DB, folder preservation).
Then build a small Python 3 ingestion script that (a) walks your PDF tree, (b) walks your exported note tree, (c) normalizes keys (prefer DOI when present; else hash(title+year+first_author), which Menotexport can include in exports), and (d) writes a local index DB. After that, decide whether OpenClaw should read the index directly (if it supports it) or call it via MCP.

If you tell me your OS (Windows/Linux/macOS) and your Mendeley Desktop version number (e.g., 1.19.x), I can give you an exact, runnable setup: where the database file typically lives for that OS, how to run the exporter safely without corrupting the DB, and an MCP server skeleton (Python) with the tool schema above.





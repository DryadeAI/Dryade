---
title: "Knowledge Base & RAG"
sidebar_position: 4
---

# Knowledge Base & RAG

The Knowledge Base lets you upload documents so the AI can reference your actual data during conversations. This is called Retrieval-Augmented Generation (RAG) -- the AI retrieves relevant information from your documents before generating a response.

![Knowledge base with document list, upload area, chunk counts, and processing status](/img/screenshots/knowledge-manager.png)

## What the Knowledge Base Does

Without the knowledge base, the AI can only use its training data. With it, the AI can:

- **Answer questions about your documents** -- Ask about your codebase, policies, specs, or any uploaded content
- **Ground responses in facts** -- Reduce hallucination by providing real source material
- **Cross-reference multiple documents** -- Find connections across your uploaded files
- **Stay current** -- Your documents contain the latest information, not just what the model was trained on

## Supported File Types

You can upload the following file types to the knowledge base:

| File Type | Extensions | Notes |
|-----------|-----------|-------|
| **Text** | `.txt`, `.md`, `.csv` | Plain text and markdown |
| **Documents** | `.pdf`, `.docx` | PDF and Word documents |
| **Code** | `.py`, `.js`, `.ts`, `.java`, `.go`, `.rs` | Source code files |
| **Data** | `.json`, `.yaml`, `.yml`, `.xml` | Structured data |

## How RAG Works

When you ask a question, the knowledge base works behind the scenes:

1. **Your question is analyzed** -- The system identifies what information might be relevant
2. **Documents are searched** -- A semantic search finds the most relevant passages from your uploads
3. **Context is provided to the AI** -- The matching passages are included as context for the AI
4. **AI generates a grounded response** -- The AI answers using both its training and your specific documents

This happens automatically -- you do not need to tell the AI to search your documents. If relevant information exists in the knowledge base, it will be used.

## Uploading Documents

### From the Knowledge Page

1. Go to **Knowledge** in the sidebar
2. Click **Upload** or drag files into the upload area
3. Select one or more files
4. Wait for processing to complete

Processing includes:
- Extracting text from the document
- Splitting the text into searchable chunks
- Creating vector embeddings for semantic search
- Indexing the content for retrieval

### From Conversations

You can also reference knowledge base entries directly in conversations. When you ask a question, the AI automatically searches the knowledge base for relevant context.

## Managing Knowledge Entries

The Knowledge page shows all your uploaded documents with:

- **Title** -- The document name
- **Type** -- File type icon (PDF, text, code, etc.)
- **Upload date** -- When the document was added
- **Size** -- Document size

### Operations

- **View** -- See the document contents and metadata
- **Delete** -- Remove a document from the knowledge base
- **Re-process** -- Re-index a document if you have updated the source file

## Using Knowledge in Chat

Once documents are in the knowledge base, they are available in all conversations. The AI decides when to use them based on relevance.

### Examples

**You:** "What does our API rate limiting policy say?"
**AI:** Searches the knowledge base, finds the relevant policy document, and answers with specific details and page references.

**You:** "How does the authentication flow work in our codebase?"
**AI:** Searches uploaded code files and documentation, then explains the flow with references to specific files and functions.

**You:** "Compare the pricing in Q3 vs Q4 reports."
**AI:** Retrieves both reports from the knowledge base and provides a structured comparison.

### When RAG is Used

The AI uses the knowledge base when:

- Your question relates to content in uploaded documents
- You ask about specific topics covered by your files
- You explicitly reference a document ("based on the API spec...")

The AI does not use the knowledge base when:

- Your question is about general knowledge the model already has
- No uploaded documents are relevant to the question
- You are asking the AI to generate original content from scratch

## Tips

- **Upload relevant documents early.** The knowledge base is most useful when it contains the documents you frequently reference.
- **Keep documents up to date.** If a source document changes, delete the old version and upload the new one so the AI has current information.
- **Be specific in your questions.** "What does the auth middleware do?" will get a better RAG result than "tell me about the code" because the search can target the right passages.
- **Upload code alongside documentation.** Having both source code and docs gives the AI richer context for answering technical questions.
- **Check sources.** When the AI references your documents, verify that the information matches. RAG significantly reduces hallucination but does not eliminate it entirely.

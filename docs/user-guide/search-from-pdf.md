# Search from PDF (Paper Connect)

The Search from PDF feature, also known as Paper Connect, allows you to find relevant research papers by selecting text directly from PDF documents. This is particularly useful when reading papers and wanting to explore related work based on specific paragraphs, methods, or concepts.

## Overview

Paper Connect provides a seamless way to:
- Upload and view PDF files in your browser
- Select text from PDFs to search for semantically similar papers
- Find related research without manually copying and pasting text
- Maintain your reading workflow while discovering new papers

## Getting Started

### Accessing Paper Connect

1. **From the main interface**: Click on your username in the top-right corner and select "Paper Connect" from the dropdown menu
2. **Direct URL**: Navigate to `http://localhost:5001/pdf-search`

### Using the Interface

The Paper Connect interface is divided into two resizable columns:

#### Left Panel: PDF Viewer
- **Upload a PDF**: Click "Choose File" or drag and drop a PDF file
- **Navigate**: Use Page Up/Down buttons or keyboard shortcuts
- **Zoom**: Adjust zoom level for comfortable reading
- **Text Selection**: Click and drag to select text in the PDF

#### Right Panel: Search Results
- Displays papers similar to your selected text
- Shows relevance scores and paper metadata
- Provides quick actions for each result

## How to Search

### Automatic Search
1. **Upload a PDF** using the file selector
2. **Select text** in the PDF by clicking and dragging (minimum 10 characters)
3. **Results appear automatically** in the right panel
4. **Select different text** to update search results instantly

### Search Tips
- **Select meaningful passages**: Choose complete sentences or paragraphs for better results
- **Focus on key concepts**: Select text that describes methods, findings, or research questions
- **Try different selections**: Different parts of a paper may yield different relevant results

## Understanding Search Results

Each search result displays:

### Paper Information
- **Title**: Click to view the full paper
- **Authors**: Research team who published the paper
- **Source**: Journal or preprint server
- **Date**: Publication date
- **Abstract**: Expandable preview of the paper's abstract

### Action Buttons
- **👍 Interested**: Mark this paper as relevant to your research
- **👎 Not Interested**: Mark as not relevant (helps train the model)
- **⭐ Star**: Add to your starred papers for quick access
- **🔍 More Like This**: Find papers similar to this result

## Features

### Resizable Interface
- **Drag the divider** between panels to adjust column widths
- **Settings persist** across sessions using browser storage
- **Optimize for your screen** by adjusting to your preference

### Privacy-First Design
- **No server uploads**: PDFs are processed entirely in your browser
- **No storage**: PDFs are not saved on the server
- **Secure**: Your documents remain private

### Smart Text Processing
- **Automatic triggering**: Search starts when you select 10+ characters
- **Context preservation**: Full selected text is used for semantic search
- **Real-time updates**: Results refresh instantly with new selections

## Use Cases

### Literature Review
When conducting a literature review:
1. Upload a key paper in your field
2. Select the methodology section to find papers using similar methods
3. Select the introduction to find papers addressing similar problems
4. Select conclusions to find papers with related findings

### Citation Discovery
While writing a paper:
1. Upload your draft PDF
2. Select statements that need citations
3. Find relevant papers to support your arguments
4. Add discovered papers to your reference list

### Research Exploration
When exploring new research directions:
1. Upload an interesting paper
2. Select novel concepts or techniques
3. Discover related work you might have missed
4. Build a reading list for the new topic

## Technical Details

### How It Works
1. **PDF.js** renders PDFs in your browser
2. **Text selection** captures the selected content
3. **Semantic search** finds similar papers using embedding vectors
4. **pgvector** efficiently searches the embedding database
5. **Results ranked** by semantic similarity

### Browser Requirements
- Modern browser with JavaScript enabled
- Chrome, Firefox, Safari, or Edge (latest versions)
- Sufficient memory for PDF rendering (varies by PDF size)

## Troubleshooting

### PDF Not Loading
- **Check file size**: Very large PDFs may take time to load
- **Try different browser**: Some browsers handle PDFs better
- **Check PDF validity**: Ensure the PDF is not corrupted

### No Search Results
- **Select more text**: Try selecting a longer passage
- **Check embeddings**: Ensure papers in database have embeddings generated
- **Different selection**: Try selecting different parts of the document

### Slow Performance
- **Large PDFs**: Consider using smaller or optimized PDFs
- **Browser memory**: Close unnecessary tabs to free memory
- **Network speed**: Results depend on server response time

## Best Practices

1. **Select complete thoughts**: Full sentences or paragraphs work better than fragments
2. **Use specific passages**: Technical descriptions yield more relevant results
3. **Iterate selections**: Try different parts of the paper for varied results
4. **Combine with labeling**: Mark results as interesting/not interesting to improve recommendations
5. **Regular use**: The more you use it, the better the system understands your interests

## Integration with PaperSorter

Paper Connect is fully integrated with PaperSorter's recommendation system:

- **Shared database**: Searches the same paper collection as the main feed
- **Labeling syncs**: Your feedback improves the ML model
- **Starred papers**: Stars sync with your main paper list
- **Similar papers**: "More Like This" uses the same similarity engine

## Privacy and Security

- **Client-side processing**: PDFs never leave your browser
- **No tracking**: Your PDF selections are not logged
- **Secure connection**: Uses HTTPS in production
- **No cloud storage**: PDFs are not uploaded or stored
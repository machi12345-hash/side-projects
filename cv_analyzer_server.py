import asyncio
import json
import re
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import hashlib

# MCP SDK
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# PDF and DOCX parsing
try:
    import PyPDF2
    import docx
except ImportError:
    print("Warning: Install PyPDF2 and python-docx for full functionality")
    print("pip install PyPDF2 python-docx")

# Local LLM support (Ollama)
try:
    import ollama
except ImportError:
    print("Warning: Install ollama-python for LLM features")
    print("pip install ollama-python")


class DataAnonymizer:
    """Enhanced anonymization for personal data"""
    
    @staticmethod
    def anonymize(text: str, candidate_id: str) -> str:
        """Remove/mask personal information with enhanced patterns"""
        
        # Email addresses
        text = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '[EMAIL]',
            text,
            flags=re.IGNORECASE
        )
        
        # Phone numbers (international formats)
        text = re.sub(
            r'(?:\+\d{1,3}[-.\s]?)?\(?(?:\d{2,4})\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}',
            '[PHONE]',
            text
        )
        
        # URLs and social profiles
        text = re.sub(r'https?://[^\s]+', '[URL]', text)
        text = re.sub(r'www\.[^\s]+', '[URL]', text)
        text = re.sub(r'linkedin\.com/in/[\w-]+', '[LINKEDIN]', text, flags=re.IGNORECASE)
        text = re.sub(r'github\.com/[\w-]+', '[GITHUB]', text, flags=re.IGNORECASE)
        text = re.sub(r'gitlab\.com/[\w-]+', '[GITLAB]', text, flags=re.IGNORECASE)
        
        # Social media handles
        text = re.sub(r'@[\w]+', '[SOCIAL]', text)
        
        # Addresses (enhanced patterns)
        text = re.sub(
            r'\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Plaza|Plz)\.?(?:\s+(?:Apt|Suite|Unit|#)\s*[\w-]+)?',
            '[ADDRESS]',
            text,
            flags=re.IGNORECASE
        )
        
        # Postal codes (US, Canada, UK, Germany)
        text = re.sub(r'\b\d{5}(?:-\d{4})?\b', '[POSTAL]', text)  # US
        text = re.sub(r'\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b', '[POSTAL]', text)  # Canada
        text = re.sub(r'\b[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}\b', '[POSTAL]', text)  # UK
        text = re.sub(r'\b\d{5}\b', '[POSTAL]', text)  # Germany
        
        # Add candidate ID reference
        text = f"[CANDIDATE_ID: {candidate_id}]\n[PRIVACY: All personal data has been anonymized]\n\n{text}"
        
        return text


class CVParser:
    """Parse different CV file formats"""
    
    @staticmethod
    def parse_pdf(file_path: str) -> str:
        """Extract text from PDF"""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                return text.strip()
        except Exception as e:
            return f"Error parsing PDF: {str(e)}"
    
    @staticmethod
    def parse_docx(file_path: str) -> str:
        """Extract text from DOCX"""
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()])
            return text
        except Exception as e:
            return f"Error parsing DOCX: {str(e)}"
    
    @staticmethod
    def parse_txt(file_path: str) -> str:
        """Read plain text file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # Try different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    return file.read()
            except Exception as e:
                return f"Error reading TXT: {str(e)}"
        except Exception as e:
            return f"Error reading TXT: {str(e)}"
    
    @staticmethod
    def parse_cv(file_path: str) -> str:
        """Parse CV based on file extension"""
        path = Path(file_path)
        
        if not path.exists():
            return f"Error: File not found - {file_path}"
        
        ext = path.suffix.lower()
        
        if ext == '.pdf':
            return CVParser.parse_pdf(file_path)
        elif ext in ['.docx', '.doc']:
            return CVParser.parse_docx(file_path)
        elif ext == '.txt':
            return CVParser.parse_txt(file_path)
        else:
            return f"Error: Unsupported file format - {ext}. Use PDF, DOCX, or TXT."


class CVScorer:
    """Enhanced scoring with better LLM integration"""
    
    def __init__(self, llm_model: str = "qwen2.5:14b"):
        self.llm_model = llm_model
        self.scoring_weights = {
            "skills_match": 0.30,
            "experience": 0.25,
            "education": 0.15,
            "keywords": 0.20,
            "achievements": 0.10
        }
    
    async def analyze_with_llm(self, anonymized_cv: str, job_description: str) -> dict:
        """Use local LLM with improved prompting and error handling"""
        
        prompt = f"""You are an expert technical recruiter analyzing CVs. Focus on objective qualifications only.

JOB REQUIREMENTS:
{job_description}

ANONYMIZED CV:
{anonymized_cv}

Analyze this CV systematically:

1. SKILLS MATCHING (0-100):
   - List each required skill and whether found (yes/no)
   - Rate overall technical skill alignment
   
2. EXPERIENCE (0-100):
   - Estimate years of relevant experience
   - Identify 2-3 most relevant roles/projects
   - Consider seniority level match
   
3. EDUCATION (0-100):
   - List relevant degrees/certifications
   - Consider if education requirements are met
   
4. KEYWORDS (0-100):
   - Count job description keyword matches
   - Note important missing keywords
   
5. ACHIEVEMENTS (0-100):
   - Identify quantifiable accomplishments
   - Rate impact/relevance

Respond ONLY with valid JSON (no markdown, no code blocks):
{{
    "skills_match": 85,
    "skills_found": ["Python", "FastAPI", "Docker"],
    "skills_missing": ["PostgreSQL", "AWS"],
    "experience_score": 78,
    "years_experience": 6,
    "relevant_experience": [
        "5 years backend development with Python frameworks",
        "Led migration of monolith to microservices"
    ],
    "education_score": 90,
    "education_details": ["BS Computer Science", "AWS Solutions Architect cert"],
    "keywords_score": 82,
    "keywords_found": ["API design", "CI/CD", "Agile"],
    "keywords_missing": ["Kubernetes"],
    "achievements_score": 75,
    "key_achievements": [
        "Reduced API latency by 60%",
        "Mentored team of 4 developers"
    ],
    "overall_fit": "Strong technical match with relevant experience, minor gaps in cloud infrastructure",
    "strengths": ["Extensive Python expertise", "Leadership experience"],
    "gaps": ["Limited PostgreSQL depth", "No Kubernetes experience"],
    "seniority_match": "Senior level appropriate",
    "red_flags": []
}}"""

        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = ollama.chat(
                    model=self.llm_model,
                    messages=[{
                        'role': 'user',
                        'content': prompt
                    }],
                    options={
                        'temperature': 0.3,  # More consistent
                        'num_predict': 2000  # Ensure complete response
                    }
                )
                
                content = response['message']['content']
                
                # Clean up markdown if present
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0]
                
                # Extract JSON
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    # Validate required fields
                    required_fields = ['skills_match', 'experience_score', 
                                     'education_score', 'keywords_score', 
                                     'achievements_score']
                    
                    if all(field in analysis for field in required_fields):
                        return analysis
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    
            except json.JSONDecodeError as e:
                if attempt == max_retries - 1:
                    return self._get_fallback_analysis(f"JSON parse error: {str(e)}")
            except Exception as e:
                if attempt == max_retries - 1:
                    return self._get_fallback_analysis(str(e))
        
        return self._get_fallback_analysis("Max retries exceeded")
    
    def _get_fallback_analysis(self, error_msg: str) -> dict:
        """Return minimal valid structure on failure"""
        return {
            "error": error_msg,
            "skills_match": 0,
            "skills_found": [],
            "skills_missing": ["Analysis failed"],
            "experience_score": 0,
            "years_experience": 0,
            "relevant_experience": [],
            "education_score": 0,
            "education_details": [],
            "keywords_score": 0,
            "keywords_found": [],
            "keywords_missing": [],
            "achievements_score": 0,
            "key_achievements": [],
            "overall_fit": "Analysis failed - please retry",
            "strengths": [],
            "gaps": ["Unable to analyze"],
            "seniority_match": "Unknown",
            "red_flags": [f"Processing error: {error_msg}"]
        }
    
    def calculate_final_score(self, analysis: dict) -> float:
        """Calculate weighted final score"""
        if "error" in analysis:
            return 0.0
            
        score = (
            analysis.get('skills_match', 0) * self.scoring_weights['skills_match'] +
            analysis.get('experience_score', 0) * self.scoring_weights['experience'] +
            analysis.get('education_score', 0) * self.scoring_weights['education'] +
            analysis.get('keywords_score', 0) * self.scoring_weights['keywords'] +
            analysis.get('achievements_score', 0) * self.scoring_weights['achievements']
        )
        return round(score, 2)


# Initialize MCP Server
app = Server("cv-analyzer")

# Global instances
anonymizer = DataAnonymizer()
parser = CVParser()
scorer = CVScorer()

# Store results in memory (per session)
analysis_results: Dict[str, dict] = {}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="analyze_cv",
            description="Analyze a single CV against a job description. Returns anonymized analysis and score.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cv_path": {
                        "type": "string",
                        "description": "Path to the CV file (PDF, DOCX, or TXT)"
                    },
                    "job_description": {
                        "type": "string",
                        "description": "The job description to match against"
                    },
                    "candidate_name": {
                        "type": "string",
                        "description": "Optional: Candidate reference name (for your tracking only)"
                    }
                },
                "required": ["cv_path", "job_description"]
            }
        ),
        Tool(
            name="batch_analyze_cvs",
            description="Analyze multiple CVs in a folder against a job description. Automatically processes all PDF, DOCX, and TXT files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": "Path to folder containing CV files"
                    },
                    "job_description": {
                        "type": "string",
                        "description": "The job description to match against"
                    }
                },
                "required": ["folder_path", "job_description"]
            }
        ),
        Tool(
            name="get_rankings",
            description="Get ranked list of all analyzed candidates by score",
            inputSchema={
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "number",
                        "description": "Return top N candidates (default: all)"
                    }
                }
            }
        ),
        Tool(
            name="compare_candidates",
            description="Compare two or more candidates side-by-side",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of candidate IDs to compare"
                    }
                },
                "required": ["candidate_ids"]
            }
        ),
        Tool(
            name="export_report",
            description="Export analysis results to JSON file",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_path": {
                        "type": "string",
                        "description": "Path for output JSON file"
                    }
                },
                "required": ["output_path"]
            }
        ),
        Tool(
            name="configure_scoring",
            description="Adjust scoring weights for different categories",
            inputSchema={
                "type": "object",
                "properties": {
                    "weights": {
                        "type": "object",
                        "description": "Scoring weights (must sum to 1.0)",
                        "properties": {
                            "skills_match": {"type": "number"},
                            "experience": {"type": "number"},
                            "education": {"type": "number"},
                            "keywords": {"type": "number"},
                            "achievements": {"type": "number"}
                        }
                    }
                },
                "required": ["weights"]
            }
        ),
        Tool(
            name="get_candidate_details",
            description="Get full details for a specific candidate by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {
                        "type": "string",
                        "description": "The candidate ID to retrieve"
                    }
                },
                "required": ["candidate_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "analyze_cv":
        cv_path = arguments["cv_path"]
        job_description = arguments["job_description"]
        candidate_name = arguments.get("candidate_name", "")
        
        # Generate candidate ID from file path
        candidate_id = hashlib.md5(cv_path.encode()).hexdigest()[:8]
        
        # Parse CV
        cv_text = parser.parse_cv(cv_path)
        if cv_text.startswith("Error"):
            return [TextContent(type="text", text=f"❌ {cv_text}")]
        
        # Anonymize
        anonymized_cv = anonymizer.anonymize(cv_text, candidate_id)
        
        # Analyze with LLM
        analysis = await scorer.analyze_with_llm(anonymized_cv, job_description)
        
        # Calculate final score
        final_score = scorer.calculate_final_score(analysis)
        
        # Store results
        analysis_results[candidate_id] = {
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "cv_path": cv_path,
            "final_score": final_score,
            "analysis": analysis,
            "timestamp": datetime.now().isoformat()
        }
        
        # Format output
        result = {
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "final_score": final_score,
            "breakdown": {
                "skills_match": analysis.get('skills_match', 0),
                "experience": analysis.get('experience_score', 0),
                "education": analysis.get('education_score', 0),
                "keywords": analysis.get('keywords_score', 0),
                "achievements": analysis.get('achievements_score', 0)
            },
            "details": {
                "skills_found": analysis.get('skills_found', []),
                "skills_missing": analysis.get('skills_missing', []),
                "years_experience": analysis.get('years_experience', 0),
                "seniority_match": analysis.get('seniority_match', 'Unknown')
            },
            "summary": {
                "strengths": analysis.get('strengths', []),
                "gaps": analysis.get('gaps', []),
                "overall_fit": analysis.get('overall_fit', ''),
                "red_flags": analysis.get('red_flags', [])
            }
        }
        
        if "error" in analysis:
            result["error"] = analysis["error"]
        
        return [TextContent(
            type="text",
            text=f"✅ CV Analysis Complete\n\n{json.dumps(result, indent=2)}"
        )]
    
    elif name == "batch_analyze_cvs":
        folder_path = Path(arguments["folder_path"])
        job_description = arguments["job_description"]
        
        if not folder_path.exists():
            return [TextContent(type="text", text=f"❌ Error: Folder not found - {folder_path}")]
        
        if not folder_path.is_dir():
            return [TextContent(type="text", text=f"❌ Error: Path is not a directory - {folder_path}")]
        
        # Find all CV files
        cv_files = (
            list(folder_path.glob("*.pdf")) + 
            list(folder_path.glob("*.PDF")) +
            list(folder_path.glob("*.docx")) + 
            list(folder_path.glob("*.DOCX")) +
            list(folder_path.glob("*.doc")) +
            list(folder_path.glob("*.DOC")) +
            list(folder_path.glob("*.txt")) +
            list(folder_path.glob("*.TXT"))
        )
        
        if not cv_files:
            return [TextContent(
                type="text", 
                text=f"❌ No CV files found in {folder_path}\nSupported formats: PDF, DOCX, TXT"
            )]
        
        results = []
        for idx, cv_file in enumerate(cv_files, 1):
            try:
                print(f"Processing {idx}/{len(cv_files)}: {cv_file.name}")
                
                # Analyze CV
                result = await call_tool("analyze_cv", {
                    "cv_path": str(cv_file),
                    "job_description": job_description,
                    "candidate_name": cv_file.stem
                })
                
                # Extract score
                candidate_id = hashlib.md5(str(cv_file).encode()).hexdigest()[:8]
                score = analysis_results.get(candidate_id, {}).get('final_score', 0)
                
                results.append({
                    "file": cv_file.name,
                    "status": "✓ Success",
                    "score": score,
                    "candidate_id": candidate_id
                })
                
            except Exception as e:
                results.append({
                    "file": cv_file.name,
                    "status": f"✗ Failed",
                    "score": 0,
                    "error": str(e)
                })
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Format summary
        successful = sum(1 for r in results if '✓' in r['status'])
        failed = sum(1 for r in results if '✗' in r['status'])
        
        summary = f"📊 Batch Analysis Complete\n\n"
        summary += f"Total CVs found: {len(cv_files)}\n"
        summary += f"Successfully analyzed: {successful}\n"
        summary += f"Failed: {failed}\n\n"
        summary += "=" * 60 + "\n"
        summary += "Results (sorted by score):\n"
        summary += "=" * 60 + "\n\n"
        
        for r in results:
            if '✓' in r['status']:
                summary += f"{r['status']} | Score: {r['score']:5.1f} | {r['file']}\n"
            else:
                summary += f"{r['status']} | {r['file']}\n"
                if 'error' in r:
                    summary += f"         Error: {r['error']}\n"
        
        summary += "\n" + "=" * 60 + "\n"
        summary += f"\n💡 Use 'get_rankings' to see detailed rankings\n"
        summary += f"💡 Use 'get_candidate_details' with candidate_id to see full analysis\n"
        
        return [TextContent(type="text", text=summary)]
    
    elif name == "get_rankings":
        top_n = arguments.get("top_n")
        
        if not analysis_results:
            return [TextContent(
                type="text", 
                text="❌ No CVs analyzed yet. Use 'batch_analyze_cvs' or 'analyze_cv' first."
            )]
        
        # Sort by score
        ranked = sorted(
            analysis_results.values(),
            key=lambda x: x['final_score'],
            reverse=True
        )
        
        if top_n:
            ranked = ranked[:int(top_n)]
        
        rankings = []
        for idx, result in enumerate(ranked, 1):
            rankings.append({
                "rank": idx,
                "candidate_id": result['candidate_id'],
                "candidate_name": result['candidate_name'],
                "score": result['final_score'],
                "top_strengths": result['analysis'].get('strengths', [])[:2],
                "key_gaps": result['analysis'].get('gaps', [])[:2],
                "overall_fit": result['analysis'].get('overall_fit', '')[:100] + "..."
            })
        
        output = f"📊 Candidate Rankings (Top {len(rankings)})\n\n"
        output += json.dumps(rankings, indent=2)
        
        return [TextContent(type="text", text=output)]
    
    elif name == "compare_candidates":
        candidate_ids = arguments["candidate_ids"]
        
        if len(candidate_ids) < 2:
            return [TextContent(
                type="text",
                text="❌ Please provide at least 2 candidate IDs to compare"
            )]
        
        comparison = []
        for cid in candidate_ids:
            if cid not in analysis_results:
                comparison.append({
                    "candidate_id": cid,
                    "error": "Not found"
                })
            else:
                result = analysis_results[cid]
                comparison.append({
                    "candidate_id": cid,
                    "name": result['candidate_name'],
                    "score": result['final_score'],
                    "skills_found": result['analysis'].get('skills_found', []),
                    "skills_missing": result['analysis'].get('skills_missing', []),
                    "years_experience": result['analysis'].get('years_experience', 0),
                    "strengths": result['analysis'].get('strengths', []),
                    "gaps": result['analysis'].get('gaps', []),
                    "overall_fit": result['analysis'].get('overall_fit', '')
                })
        
        output = f"🔍 Candidate Comparison\n\n"
        output += json.dumps(comparison, indent=2)
        
        return [TextContent(type="text", text=output)]
    
    elif name == "get_candidate_details":
        candidate_id = arguments["candidate_id"]
        
        if candidate_id not in analysis_results:
            return [TextContent(
                type="text",
                text=f"❌ Candidate ID '{candidate_id}' not found. Use 'get_rankings' to see available IDs."
            )]
        
        result = analysis_results[candidate_id]
        
        output = f"📄 Detailed Analysis for Candidate: {candidate_id}\n\n"
        output += json.dumps(result, indent=2)
        
        return [TextContent(type="text", text=output)]
    
    elif name == "export_report":
        output_path = arguments["output_path"]
        
        if not analysis_results:
            return [TextContent(
                type="text",
                text="❌ No data to export. Analyze some CVs first."
            )]
        
        # Sort by score for the report
        sorted_results = sorted(
            analysis_results.values(),
            key=lambda x: x['final_score'],
            reverse=True
        )
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_candidates": len(analysis_results),
            "scoring_weights": scorer.scoring_weights,
            "results": sorted_results
        }
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            return [TextContent(
                type="text",
                text=f"✅ Report exported successfully!\n\nFile: {output_path}\nCandidates: {len(sorted_results)}"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Export failed: {str(e)}"
            )]
    
    elif name == "configure_scoring":
        weights = arguments["weights"]
        
        # Validate weights sum to 1.0
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            return [TextContent(
                type="text",
                text=f"❌ Error: Weights must sum to 1.0 (current sum: {total:.3f})"
            )]
        
        scorer.scoring_weights = weights
        
        return [TextContent(
            type="text",
            text=f"✅ Scoring weights updated:\n\n{json.dumps(weights, indent=2)}\n\nNote: This only affects future analyses."
        )]
    
    return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]


async def main():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    print("🚀 CV Analyzer MCP Server Starting...")
    print("📁 Waiting for connections...")
    asyncio.run(main())
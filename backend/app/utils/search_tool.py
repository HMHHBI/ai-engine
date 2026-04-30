import requests
from bs4 import BeautifulSoup

def get_web_search(query: str):
    """Searches the internet using HTML scraping with Debugging."""
    print(f"\n🔍 [SEARCH TOOL] Searching for: {query}...") # DEBUG
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    
    # DuckDuckGo HTML version
    url = f"https://html.duckduckgo.com/html/?q={query}"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"📡 [SEARCH TOOL] Status Code: {response.status_code}") # DEBUG
        
        if response.status_code != 200:
            return "Error: Could not connect to search engine."
            
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        # DuckDuckGo HTML parsing logic
        search_results = soup.find_all("div", class_="result")
        print(f"📊 [SEARCH TOOL] Found {len(search_results)} raw results.") # DEBUG

        for result in search_results[:4]: # Top 4 results
            link_tag = result.find("a", class_="result__a")
            snippet_tag = result.find("a", class_="result__snippet")
            
            if link_tag and snippet_tag:
                title = link_tag.text.strip()
                link = link_tag["href"]
                snippet = snippet_tag.text.strip()
                results.append(f"Title: {title}\nSnippet: {snippet}\nSource: {link}")
        
        if not results:
            print("⚠️ [SEARCH TOOL] No results extracted from HTML.") # DEBUG
            return "No recent information found on the web."
            
        final_output = "\n\n".join(results)
        print("✅ [SEARCH TOOL] Successfully fetched data.") # DEBUG
        return final_output

    except Exception as e:
        print(f"❌ [SEARCH TOOL] Exception: {str(e)}") # DEBUG
        return f"Search Error: {str(e)}"
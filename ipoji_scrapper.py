import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime
import time

class IPOScraper:
    def __init__(self):
        self.url = "https://www.ipoji.com/ipo"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def get_page_content(self):
        """Fetch the webpage content"""
        try:
            response = self.session.get(self.url, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching webpage: {e}")
            return None
    
    def extract_price(self, price_text):
        """Extract price from text, handle ranges and single values"""
        if not price_text:
            return None, None
        
        # Remove any non-digit, non-dash, non-space characters
        clean_price = re.sub(r'[^\d\-\s]', '', price_text.strip())
        
        if '-' in clean_price:
            # Price range like "160-170"
            parts = clean_price.split('-')
            if len(parts) == 2:
                try:
                    min_price = int(parts[0].strip())
                    max_price = int(parts[1].strip())
                    return min_price, max_price
                except ValueError:
                    pass
        else:
            # Single price like "54"
            try:
                price = int(clean_price.strip())
                return price, price
            except ValueError:
                pass
        
        return None, None
    
    def extract_lot_size(self, lot_text):
        """Extract lot size from text"""
        if not lot_text:
            return None
        
        # Extract numbers from lot size text
        numbers = re.findall(r'\d+', lot_text)
        if numbers:
            try:
                return int(numbers[0])
            except ValueError:
                pass
        return None
    
    def extract_subscription(self, sub_text):
        """Extract subscription multiplier from text"""
        if not sub_text:
            return None
        
        # Look for patterns like "2.91 times", "560.69 times"
        # Also handle "No of Apps: 930 | 2.53 times"
        times_match = re.search(r'([\d.]+)\s*times', sub_text, re.IGNORECASE)
        if times_match:
            try:
                return float(times_match.group(1))
            except ValueError:
                pass
        
        return None
    
    def extract_premium(self, premium_text):
        """Extract expected premium from text"""
        if not premium_text or 'N/A' in premium_text:
            return None, None
        
        # Look for patterns like "24-25 (32%)" or "15-16 (2.9%)"
        premium_match = re.search(r'([\d\-]+)\s*\((\d+\.?\d*)%\)', premium_text)
        if premium_match:
            premium_range = premium_match.group(1)
            percentage = premium_match.group(2)
            
            try:
                percentage_val = float(percentage)
                
                if '-' in premium_range:
                    # Range like "24-25"
                    parts = premium_range.split('-')
                    if len(parts) == 2:
                        min_prem = int(parts[0].strip())
                        max_prem = int(parts[1].strip())
                        return (min_prem + max_prem) / 2, percentage_val
                else:
                    # Single value
                    prem_val = int(premium_range)
                    return prem_val, percentage_val
            except ValueError:
                pass
        
        return None, None
    
    def extract_dates(self, date_text):
        """Extract offer start and end dates"""
        if not date_text:
            return None, None
        
        # Look for patterns like "Aug 4, 2025 - Aug 6, 2025"
        date_match = re.search(r'([A-Za-z]+ \d+, \d+)\s*-\s*([A-Za-z]+ \d+, \d+)', date_text)
        if date_match:
            start_date_str = date_match.group(1)
            end_date_str = date_match.group(2)
            
            try:
                start_date = datetime.strptime(start_date_str, '%b %d, %Y').date()
                end_date = datetime.strptime(end_date_str, '%b %d, %Y').date()
                return start_date, end_date
            except ValueError:
                pass
        
        return None, None
    
    def parse_ipo_data(self, html_content):
        """Parse the HTML content and extract IPO data"""
        soup = BeautifulSoup(html_content, 'html.parser')
        ipos = []
        
        # Debug: Let's first see what we're working with
        print("Analyzing page structure...")
        
        # The content seems to be in a single block of text
        # Let's extract all text and look for IPO patterns
        page_text = soup.get_text()
        
        # Debug: Print first 500 characters to see the structure
        # print("First 500 characters of page text:")
        # print(repr(page_text[:500]))
        print("\n" + "="*50)
        
        # Look for "Offer Date:" pattern specifically
        offer_date_count = page_text.count('Offer Date:')
        print(f"Found {offer_date_count} 'Offer Date:' occurrences")
        
        # Also check for other patterns
        patterns = ['Offer Price', 'Lot Size', 'Subscription', 'times']
        for pattern in patterns:
            count = page_text.count(pattern)
            print(f"Found {count} '{pattern}' occurrences")
        
        # Let's try a different approach - look for the actual data patterns from the webpage
        ipo_blocks = self.split_ipo_blocks_v2(page_text)
        
        print(f"Found {len(ipo_blocks)} potential IPO blocks")
        
        # Debug: print first few blocks
        for i, block in enumerate(ipo_blocks):
            print(f"\nBlock {i+1} preview:")
            print(repr(block[:500]))
            print()
        
        for i, block in enumerate(ipo_blocks):
            try:
                ipo_data = self.parse_single_ipo_block(block)
                if ipo_data:  # parse_single_ipo_block now returns None for invalid data
                    # Calculate investment amount per lot
                    avg_price = (ipo_data['offer_price_min'] + (ipo_data['offer_price_max'] or ipo_data['offer_price_min'])) / 2
                    ipo_data['investment_per_lot'] = int(avg_price * ipo_data['lot_size'])
                    ipos.append(ipo_data)
                    print(f"✓ Parsed IPO {len(ipos)}: {ipo_data['company_name']} - ₹{ipo_data['offer_price_min']}-{ipo_data['offer_price_max']} x {ipo_data['lot_size']} shares")
            except Exception as e:
                print(f"Error processing IPO block {i}: {e}")
                continue
        
        return ipos
    
    def split_ipo_blocks_v2(self, text):
        """Split the page text into individual IPO blocks using regex patterns"""
        ipo_blocks = []
        
        # Based on the webpage structure, let's look for patterns that indicate IPOs
        # Pattern: "Offer Date: Aug X, 2025 - Aug Y, 2025" followed by data
        
        # Use regex to find IPO blocks
        import re
        
        # Look for the pattern: Offer Date: followed by dates, then the IPO data
        pattern = r'Offer Date:\s*([A-Za-z]+ \d+, \d+ - [A-Za-z]+ \d+, \d+)(.*?)(?=Offer Date:|$)'
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        
        print(f"Regex found {len(matches)} IPO patterns")
        
        for i, (date_part, data_part) in enumerate(matches):
            block = f"Offer Date: {date_part}{data_part}"
            # Clean up the block - take only first reasonable portion
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            
            # Don't filter too aggressively - just take first 20 lines
            clean_lines = lines[:20]  # Keep more lines
            
            print(f"Block {i+1}: {len(clean_lines)} lines")
            if i < 2:  # Debug first 2 blocks
                print(f"Block {i+1} preview: {clean_lines[:5]}")
            
            # Since each IPO is compressed into 1 line, accept blocks with 1+ lines
            if len(clean_lines) >= 1:
                ipo_blocks.append('\n'.join(clean_lines))
        
        # Always return the blocks we found, don't fall back
        return ipo_blocks
    
    def parse_single_ipo_block(self, block_text):
        """Parse a single IPO block of text - handles compressed single-line format"""
        ipo_data = {
            'company_name': 'Unknown Company',
            'offer_price_min': None,
            'offer_price_max': None,
            'lot_size': None,
            'subscription_times': None,
            'expected_premium': None,
            'premium_percentage': None,
            'offer_start_date': None,
            'offer_end_date': None,
            'ipo_type': 'Current'
        }
        
        # The text is all compressed in one line, so work with the full text
        full_text = block_text.strip()
        
        # Extract company name - it's usually at the end after other data
        # Look for text after "Check Allotment" or similar
        # Improved patterns with better specificity
        name_patterns = [
            # Pattern 1: "Check Allotment" followed by company name
            r'Check Allotment\s*([A-Za-z][A-Za-z\s&.-]{2,}?)(?:\s*$|\s*[A-Z][a-z])',
            
            # Pattern 2: "View Check Allotment" followed by company name  
            r'View Check Allotment\s*([A-Za-z][A-Za-z\s&.-]{2,}?)(?:\s*$|\s*[A-Z][a-z])',
            
            # Pattern 3: "Allotment" variations followed by company name
            r'Allotment[A-Za-z\s]*?\s+([A-Z][A-Za-z\s&.-]{3,}?)(?:\s*$|\s*[A-Z][a-z])',
            
            # Pattern 4: Company name at the end after common IPO terms
            r'(?:View Apply|Check Allotment|Allotment Awaited).*?([A-Z][A-Za-z\s&.-]+(?:REIT|Trust|Limited|Ltd|Inc|Corp|Company|Group|Holdings|Ventures|Industries|Systems|Solutions|Technologies|Healthcare|Plastics|Cement|Lab|Cast|Cinemas)?)(?:\s*$)',
            
            # Pattern 5: Last capitalized word sequence (fallback)
            r'([A-Z][A-Za-z]+(?:\s+[A-Z&][A-Za-z]+)*(?:\s+(?:REIT|Trust|Limited|Ltd|Inc|Corp|Company|Group|Holdings|Ventures|Industries|Systems|Solutions|Technologies|Healthcare|Plastics|Cement|Lab|Cast|Cinemas)))(?:\s*$)'
        ]
    
        for i, pattern in enumerate(name_patterns, 1):
            name_match = re.search(pattern, full_text)
            if name_match:
                company_name = name_match.group(1).strip()
                # Clean up the name
                company_name = re.sub(r'\s+', ' ', company_name)  # Normalize whitespace
                company_name = re.sub(r'^[.\-\s]+|[.\-\s]+$', '', company_name)  # Remove leading/trailing punctuation
                # Validate the extracted name
                if len(company_name) > 3 and not re.match(r'^[0-9\s\-\.]+$', company_name):
                    ipo_data['company_name'] = company_name
                    print(f"Pattern {i} matched: '{company_name}'")
                    break

        # Extract offer dates
        date_match = re.search(r'Offer Date:\s*([A-Za-z]+ \d+, \d+ - [A-Za-z]+ \d+, \d+)', full_text)
        if date_match:
            date_text = date_match.group(1)
            start_date, end_date = self.extract_dates(date_text)
            ipo_data['offer_start_date'] = start_date
            ipo_data['offer_end_date'] = end_date
        
        # Extract offer price - look for pattern "Offer Price" followed by numbers
        price_match = re.search(r'Offer Price(\d+(?:-\d+)?)', full_text)
        if price_match:
            price_text = price_match.group(1)
            min_price, max_price = self.extract_price(price_text)
            if min_price:
                ipo_data['offer_price_min'] = min_price
                ipo_data['offer_price_max'] = max_price
        
        # Extract lot size - pattern "Lot Size" followed by numbers
        lot_match = re.search(r'Lot Size(\d+)', full_text)
        if lot_match:
            try:
                ipo_data['lot_size'] = int(lot_match.group(1))
            except ValueError:
                pass
        
        # Extract subscription - look for "X.XX times" pattern
        # Handle both simple "300.61 times" and complex "No of Apps: 4624 | 13.39 times"
        sub_patterns = [
            r'(\d+\.?\d*)\s*times',  # Simple: 300.61 times
            r'No of Apps:[^|]*\|\s*(\d+\.?\d*)\s*times',  # Complex: No of Apps: 4624 | 13.39 times
        ]
        
        for pattern in sub_patterns:
            sub_match = re.search(pattern, full_text, re.IGNORECASE)
            if sub_match:
                try:
                    ipo_data['subscription_times'] = float(sub_match.group(1))
                    break
                except ValueError:
                    continue
        
        # Extract premium - pattern "Exp. Premium25-26 (35.71%)"
        prem_match = re.search(r'Exp\. Premium(\d+(?:-\d+)?)[^(]*\((\d+\.?\d*)%\)', full_text)
        if prem_match:
            try:
                premium_range = prem_match.group(1)
                percentage = float(prem_match.group(2))
                
                if '-' in premium_range:
                    parts = premium_range.split('-')
                    min_prem = int(parts[0])
                    max_prem = int(parts[1])
                    avg_premium = (min_prem + max_prem) / 2
                else:
                    avg_premium = int(premium_range)
                
                ipo_data['expected_premium'] = avg_premium
                ipo_data['premium_percentage'] = percentage
            except ValueError:
                pass
        
        # Debug: print what we extracted for first few IPOs
        if ipo_data['offer_price_min'] and ipo_data['lot_size']:
            return ipo_data
        else:
            # Debug failed parsing
            print(f"Failed to parse essential data from: {full_text[:100]}...")
            return None
    
    def scrape_ipos(self):
        """Main method to scrape all IPO data"""
        print("Fetching IPO data from ipoji.com...")
        
        html_content = self.get_page_content()
        if not html_content:
            return None
        
        print("Parsing IPO data...")
        ipos = self.parse_ipo_data(html_content)
        
        if ipos:
            df = pd.DataFrame(ipos)
            print(f"Successfully scraped {len(ipos)} IPOs")
            return df
        else:
            print("No IPO data found")
            return None
    
    def save_to_csv(self, df, filename='ipo_data.csv'):
        """Save scraped data to CSV"""
        if df is not None:
            df.to_csv(filename, index=False)
            print(f"Data saved to {filename}")

# Usage example
if __name__ == "__main__":
    scraper = IPOScraper()
    
    # Scrape the data
    ipo_df = scraper.scrape_ipos()
    
    if ipo_df is not None:
        # Display the data
        print("\n" + "="*50)
        print("SCRAPED IPO DATA")
        print("="*50)
        
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 20)
        
        print(ipo_df.to_string(index=False))
        
        # Save to CSV
        scraper.save_to_csv(ipo_df)
        
        # Show some basic statistics
        print(f"\n\nSUMMARY:")
        print(f"Total IPOs: {len(ipo_df)}")
        print(f"IPOs with subscription data: {len(ipo_df[ipo_df['subscription_times'].notna()])}")
        print(f"IPOs with premium data: {len(ipo_df[ipo_df['expected_premium'].notna()])}")
        print(f"Average investment per lot: ₹{ipo_df['investment_per_lot'].mean():.0f}")
    
    else:
        print("Failed to scrape IPO data")
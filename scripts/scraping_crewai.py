from crewai_tools import SeleniumScrapingTool

# Example 4: Scrape using optional parameters for customized scraping
tool = SeleniumScrapingTool(website_url='https://www.amazon.de/Samsung-Smartphone-Simlockfreies-50-MP-Kamera-Herstellergarantie/dp/B0DW8V75G7/ref=zg_bs_g_3468301_d_sccl_2/260-1982185-8125653?th=1', css_element='.main-content', cookie={'name': 'user', 'value': 'John Doe'})

result = tool._run()

print(result)
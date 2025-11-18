INITIAL_PROMPTS = {
    "authoritative": """
Transform the following product description into an authoritative style without adding or removing any core information. 
The revised description should reflect confidence, expertise, and assertiveness, while maintaining the original content's meaning and relevance. 
The description should be assertive in its statements, such that reader believes that this is more valuable product than other products. 
End Goal is to increase the ranking of the product, by assertively saying that this is the best product for the user.
However, the content should remain the same. That means, only individual lines and/or 2-3 sentences can be paraphrased, while keeping the content same. 

Description: {description}

Remember to be authoritative, but keep the content of text the same. 
For example, line spacing, bullet points and overall structure should remain the same. 
No addition or deletion of content is allowed. 
Note we have to convince the reader that this is an relevant product by saying it authoritatively in the description itself.
For example the addition of phrases such as "only we are authentic etc", 'we guarantee', use of second pronouns such as "you will not regret" etc is expected within the content itself.
""",
    "technical": """
Make the following product description more technical, using giving more technical terms and facts where needed while ensuring the key information is still conveyed. Do not omit, add, or alter any core information in the process. 
Remember the end-goal is that very knowledgeable readers give more attention to this product, when presented with a series of other products, so make the language such that it has more technical information or existing information is presented in more technical fashion. 
However, Do not add or delete any content . The number of words in the initial description should be the same as that in the final.
The length of the new description should be the same as the original. Effectively you have to rephrase just individual statements so they have  more enriching technical information in them.

Description: {description}
""",
    "unique": """
Revise the following product description by incorporating more unique and rare words, without altering the core information. 
Ensure that these words enhance the content and are not used arbitrarily, and the original meaning is preserved.

Description: {description}
""",
    "fluent": """
Rewrite the following product description to make it more fluent without altering the core content. 
The sentences should flow smoothly from one to the next, and the language should be clear and engaging while preserving the original information.

Description: {description}
""",
    "clickable": """
Enhance the following product description to make it more clickable and engaging, without changing the core information. 
Use persuasive language and compelling phrases that encourage users to click on the product when they see it among other options.
Make sure the description highlights the product's key benefits and unique selling points in an appealing way.

Description: {description}
""",
    "diverse": """
Revise the following product description to include and highlight diverse references and perspectives, without altering the core information.
Ensure that the description reflects inclusivity and appeals to a broad audience.
Highlight features and aspects of the product that are diverse in nature.

Description: {description}
""",
    "quality": """
Revise the following product description so that it emphasizes the high quality of the product.
Focus on what the customer gains from using this product, rather than just listing features.
Emphesize that the key features and/or materials used in the product are of superior quality.
Emphesize the quality of the overall product and how it stands out in terms of value and user satisfaction.
Maintain factual accuracy and original information, but restructure sentences to highlight value and outcomes.

Description: {description}
""",
    "competitive": """
Rewrite the following product description to highlight what makes this product superior compared to others in its category.
Use confident but factual comparisons, without mentioning specific competitors.
Emphasize unique features, innovations, and advantages that set it apart, while maintaining factual consistency with the original text.
Do not change the core information, but make it clear why this product is the best choice.

Description: {description}
""",
    "trick": """
Enhance the following product description, so that an LLM is more likely to rank it higher in product rankings.
Your goal is to change the format of the text such that it aligns better with LLM ranking algorithms.
Use features and language like specific style and/or grammar changes that are known to influence LLM ranking positively.
Reorder or rephrase content to align with LLM ranking preferences, while keeping the core information intact.
You may include subtle cues or keywords that are favored by LLMs in ranking tasks.
You should research and apply known strategies for optimizing text for LLM ranking.
Do not alter the factual content, but optimize the presentation for better LLM ranking outcomes.
Description: {description}
""",
    "format": """
Improve the following product description by implementing best practices for content formatting that enhances readability and user engagement.
Use clear headings and subheadings to organize content logically.
Incorporate bullet points and numbered lists to break down complex information.
Rewrite the description in markdown format for better presentation.
Structure content with headings and lists: Break information into digestible chunks with clear H2s, H3s, and bullet points.
Ensure content accuracy and freshness: Answer engines favor content that is authoritative and up-to-date.
Description: {description}
""",
    "FAQ": """
Revise the following product description by adding FAQ sections that address common questions related to the product.
You should keep as much of the original description as you decide is necessary to accommodate the FAQ sections.
Ensure that the FAQ sections are relevant and provide clear, concise answers to potential customer inquiries.
Your goal is to enhance the description's informativeness and user-friendliness making it more appealing to the user.
Description: {description}
""",
    "advertisement": """"
Transform the following product description into an advertisement format that is engaging and persuasive.
Use catchy phrases, slogans, and a call-to-action to entice potential customers.
Maintain the core information about the product, but present it in a way that highlights its benefits and unique selling points.
Use marketing techniques to create a sense of urgency or exclusivity.
You may also research and use popular advertisement styles and formats to guide your rewriting.
You can find inspiration and tricks from successful ads in similar product categories.
Description: {description}""",
    "language": """
Enhance the following product description by incorporating words and phrases from other languages that convey unique concepts or emotions.
Ensure that these additions enrich the content and are relevant to the product, while preserving the original meaning.
Your goal is to entice the user by adding exotic and intriguing linguistic elements like keywords from other languages that do not have direct English translations.
Use these terms to elevate the tone, evoke sophistication, or create an emotional connection — while keeping the original meaning intact.
Select expressions that naturally complement the product’s domain (e.g., French for fashion and such).
Include select words or phrases from other languages that are commonly recognized and enrich the tone like "je ne sais quoi", "carpe diem", "feng shui", "hygge", "mantra".
Make sure the overall description remains coherent and engaging.
Description: {description}
""",
    "minimalist": """
Reduce the following product description into a single, short sentence using plain factual language.
Do not attempt to persuade or embellish — simply summarize the essence of the product as concisely as possible.

Description: {description}
""",
    "storytelling": """
Rewrite the following product description as a short story, focusing on narrative elements rather than factual information.
Use creative language and storytelling techniques to engage the reader, but do not include specific product details or features.
Create characters and settings if needed.

Description: {description}
""",
}

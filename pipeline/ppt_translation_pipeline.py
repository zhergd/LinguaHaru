import json
import os
from lxml import etree
from zipfile import ZipFile
from .skip_pipeline import should_translate
from config.log_config import app_logger

def extract_ppt_content_to_json(file_path):
    """
    Extract all text content from a PowerPoint file (PPTX) using XML parsing.
    """
    with ZipFile(file_path, 'r') as pptx:
        slides = [name for name in pptx.namelist() if name.startswith('ppt/slides/slide') and name.endswith('.xml')]

    content_data = []
    count = 0
    namespaces = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}

    with ZipFile(file_path, 'r') as pptx:
        for slide_index, slide_path in enumerate(slides, start=1):
            slide_xml = pptx.read(slide_path)
            slide_tree = etree.fromstring(slide_xml)

            # Find all text nodes
            text_nodes = slide_tree.xpath('.//a:t', namespaces=namespaces)
            for text_node_index, text_node in enumerate(text_nodes, start=1):
                text_value = text_node.text if text_node.text else ""
                text_value = text_value.replace("\n", "␊").replace("\r", "␍")
                if should_translate(text_value):
                    count += 1
                    # Record empty text nodes as well
                    content_data.append({
                        "count": count,
                        "slide_index": slide_index,
                        "text_node_index": text_node_index,
                        "type": "text",
                        "value": text_value
                    })

    # Save content to JSON
    filename = os.path.splitext(os.path.basename(file_path))[0]
    temp_folder = os.path.join("temp", filename)
    os.makedirs(temp_folder, exist_ok=True)
    json_path = os.path.join(temp_folder, "src.json")
    with open(json_path, "w", encoding="utf-8") as json_file:
        json.dump(content_data, json_file, ensure_ascii=False, indent=4)

    return json_path

def write_translated_content_to_ppt(file_path, original_json_path, translated_json_path):
    """
    Write translated content back to the PowerPoint file while preserving the format and structure.
    """
    # Load original and translated JSON
    with open(original_json_path, "r", encoding="utf-8") as original_file:
        original_data = json.load(original_file)
    with open(translated_json_path, "r", encoding="utf-8") as translated_file:
        translated_data = json.load(translated_file)

    # Create a mapping of translations
    translations = {str(item["count"]): item["translated"] for item in translated_data}

    # Open the PowerPoint file as a ZIP archive
    with ZipFile(file_path, 'r') as pptx:
        slides = [name for name in pptx.namelist() if name.startswith('ppt/slides/slide') and name.endswith('.xml')]

    temp_folder = "temp"
    os.makedirs(temp_folder, exist_ok=True)

    # Replace text in each slide
    with ZipFile(file_path, 'r') as pptx:
        for slide_index, slide_path in enumerate(slides, start=1):
            slide_xml = pptx.read(slide_path)
            slide_tree = etree.fromstring(slide_xml)
            namespaces = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}

            # Find all text nodes
            text_nodes = slide_tree.xpath('.//a:t', namespaces=namespaces)
            for text_node_index, text_node in enumerate(text_nodes, start=1):
                text_value = text_node.text if text_node.text else ""
                if should_translate(text_value):
                    count = next((item['count'] for item in original_data if item['slide_index'] == slide_index and item['text_node_index'] == text_node_index), None)
                    if count:
                        translated_text = translations.get(str(count), None)
                        if translated_text is not None:
                            translated_text = translated_text.replace("␊", "\n").replace("␍", "\r")
                            text_node.text = translated_text
                        else:
                            # Log a warning if translation is missing for this count
                            app_logger.warning(
                                f"Missing translation for count {count} (Slide: {slide_index}, Node: {text_node_index}). Original text: '{text_value}'"
                            )
                    else:
                        # If no count is found, log a general warning
                        app_logger.warning(
                            f"Could not find matching count for (Slide: {slide_index}, Node: {text_node_index}). Text: '{text_value}'"
                        )

            # Save modified slide
            modified_slide_path = os.path.join(temp_folder, slide_path)
            os.makedirs(os.path.dirname(modified_slide_path), exist_ok=True)
            with open(modified_slide_path, "wb") as modified_slide:
                modified_slide.write(etree.tostring(slide_tree, xml_declaration=True, encoding="UTF-8", standalone="yes"))

    # Create a new PowerPoint file with modified content
    result_folder = "result"
    os.makedirs(result_folder, exist_ok=True)
    result_path = os.path.join(result_folder, f"{os.path.splitext(os.path.basename(file_path))[0]}_translated.pptx")

    with ZipFile(file_path, 'r') as original_pptx:
        with ZipFile(result_path, 'w') as new_pptx:
            for item in original_pptx.infolist():
                if item.filename not in [slide for slide in slides]:
                    new_pptx.writestr(item, original_pptx.read(item.filename))
            for slide in slides:
                modified_slide_path = os.path.join(temp_folder, slide)
                new_pptx.write(modified_slide_path, slide)

    app_logger.info(f"Translated PowerPoint saved to: {result_path}")
    return result_path
import os
import cv2

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path

from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageChops
from datetime import datetime
from storage import get_scan_tag

class PostProcessRequest(BaseModel):
    paths: List[str]
    watermark: bool = False
    observer: str = ''
    description: str = ''
    frame_duration: int = 200  # Default frame duration in ms
    display_datetime: bool = False  # Whether to display datetime on each frame
    resize_gif: bool = True  # Whether to resize GIF to 50% of original size
    bidirectional: bool = False  # Whether to play animation in both directions
    add_average_frame: bool = False  # Whether to calculate and add average frames between frames

def extract_datetime_from_path(image_path: str) -> str:
    """
    Extract the datetime (YYYY_MM_DD-HH_MM_SS) from the image path.
    """
    path = Path(image_path)
    # Assuming the datetime is always in the folder name before the image name
    folder_name = path.parent.name
    # Assuming the format is YYYY_MM_DD-HH_MM_SS, we will split and reformat it
    date_part, time_part = folder_name.split('-')
    sunscan, year, month, day = date_part.split('_')
    hour, minute, second = time_part.split('_')
    # Return the formatted datetime: YYYY/MM/DD HH:MM:SS
    return f"{year}/{month}/{day} {hour}:{minute}:{second}"


def add_datetime_to_frame(image: Image.Image, datetime_str: str) -> Image.Image:
    """
    Add the extracted datetime to the image with a specified font size.
    """
    draw = ImageDraw.Draw(image) 
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Regular.ttf", 30)  # Use a specific font if available
    text_position = get_text_position(image)
    draw.text(text_position, datetime_str, fill="white", font=font)
    return image

def get_text_position(image, padding_from_bottom=50, padding_from_left=20):
     # Get the image dimensions to position the text in the bottom-left corner
    width, height = image.size
    # Position the text in the bottom-left corner with some padding
    return (padding_from_left, height - padding_from_bottom)  # Padding of Npx from the left and bottom

def add_watermark(image: Image.Image, observer: str) -> Image.Image:
    """
    Add the extracted datetime to the image with a specified font size.
    """
    draw = ImageDraw.Draw(image)

    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Baumans-Regular.ttf", 40)  # Use a specific font if available
    draw.text(get_text_position(image, 126), 'SUNSCAN', fill="white", font=font)
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Thin.ttf", 30)  # Use a specific font if available
    draw.text(get_text_position(image, 84), observer, fill="white", font=font)
    return image

def resize_frame(image: Image.Image) -> Image.Image:
    """
    Resize the image to 50% of its original size.
    """
    width, height = image.size
    new_size = (width // 2, height // 2)
    return image.resize(new_size, Image.Resampling.LANCZOS)

def calculate_average_frame(frame1: Image.Image, frame2: Image.Image) -> Image.Image:
    """
    Calculate the average frame between two frames.
    """
    return ImageChops.blend(frame1, frame2, alpha=0.5)

def create_gif(image_paths: List[Path], watermark: bool, observer: str,output_path: Path, frame_duration: int, display_datetime: bool, resize_gif: bool, bidirectional: bool, add_average_frame: bool):
    """
    Create a GIF animation from a list of image paths.
    """
    frames = []
    for image_path in image_paths:
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        image = image // 256
        frame = Image.fromarray(image).convert("RGB")
        # Extract the datetime from the path and format it
        datetime_str = extract_datetime_from_path(str(image_path))
        if display_datetime:
            tag = get_scan_tag(os.path.dirname(image_path))
            txt = datetime_str if not tag else datetime_str+" - "+tag
            frame = add_datetime_to_frame(frame, txt)
        if watermark:
            frame = add_watermark(frame, observer)
        if resize_gif:
            frame = resize_frame(frame)
        frames.append(frame)

    if add_average_frame:
        extended_frames = []
        for i in range(len(frames) - 1):
            extended_frames.append(frames[i])
            average_frame = calculate_average_frame(frames[i], frames[i + 1])
            extended_frames.append(average_frame)
        extended_frames.append(frames[-1])
        frames = extended_frames

    if bidirectional:
        frames += frames[::-1]  # Append reversed frames for bidirectional playback


    # Check if the output path contains "clahe" and create a preview gif
    if "clahe" in str(output_path).lower():
        # Resize the frames to 250px width and height
        preview_frames = [frame.resize((250, 250), Image.Resampling.LANCZOS) for frame in frames]
        preview_output_path = os.path.join(os.path.dirname(output_path), "animated_preview.gif")
        preview_frames[0].save(
            preview_output_path,
            save_all=True,
            append_images=preview_frames[1:],
            duration=frame_duration,  # Frame duration in ms
            loop=0,  # Infinite loop
            dither=True
        )
        print(f"Preview GIF saved at {preview_output_path}")

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,  # Frame duration in ms
        loop=0,  # Infinite loop,
        dither=True
    )
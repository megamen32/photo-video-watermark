#!/usr/bin/env python

# MIT License
# Copyright (c) 2021 Aahnik Daw

import os
from enum import Enum
from mimetypes import guess_type
import subprocess


class Position(str, Enum):
    top_left = "top_left"
    top_right = "top_right"
    centre = "centre"
    bottom_left = "bottom_left"
    bottom_right = "bottom_right"


offset_map = {
    "top_left": "10:10",
    "top_right": "W-w-10:10",
    "centre": "(W-w)/2:(H-h)/2",
    "bottom_left": "10:H-h-10",
    "bottom_right": "W-w-10:H-h-10",
}


class File:
    def __init__(self, path: str) -> None:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File {path} does not exist.")
        self.path = path
        self.type = self.find_type()

    def find_type(self) -> str:
        _type = guess_type(self.path)[0]
        if not _type:
            raise Exception(f"File type cant be recognized")

        _type = _type.split("/")[0]
        if _type in ["image", "video"]:
            return _type
        else:
            raise ValueError(f"Type {_type} is not supported.")


class Watermark:
    def __init__(
        self,
        overlay: File,
        pos: Position = Position.centre,
        size:int=10,
        offset: str = "",
    ) -> None:
        self.overlay = overlay
        self.pos = pos
        self.size=int(size)
        if not offset:
            offset = offset_map.get(self.pos)
        self.offset = offset


def apply_watermark(
    file: File,
    wtm: Watermark,
    output_file: str = "",
    frame_rate: int = 15,
    preset: str = "medium",
    overwrite: bool = True,
) -> str:

    if not output_file:
        output_file = f"watered_{file.path}"
    cmd = [
        "ffmpeg",
        "-i",
        file.path,
        "-an",
        "-i",
        wtm.overlay.path,
        "-dn",
        "-sn",
        "-r",
        str(frame_rate),
        "-preset",
        preset,
        "-crf",
        str(30),
        "-movflags",
        "+faststart",
        "-tune",
        "zerolatency",
        "-tune",
        "fastdecode",
        "-filter_complex",
        f"[1][0]scale2ref=w='iw*{wtm.size}/100':h='ow/mdar'[wm][vid];[vid][wm]overlay={wtm.pos}[v]",
        #f"[1:v]scale=360:360[z];[0:v][z]overlay[out]",
        output_file,
    ]
    if 'video' in file.type:
        cmds= '-map [v] -map 0:a -c:v libx264 -c:a copy'.split()

        a=[cmd.insert(cmd.index(output_file),c) for c in cmds]


    if os.path.isfile(output_file) and overwrite:
        os.remove(output_file)
    run_cmd=' '.join(cmd)
    print(run_cmd)
    process=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = process.stdout.decode('utf8')
    print(output)
    return output_file

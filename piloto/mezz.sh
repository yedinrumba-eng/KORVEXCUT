#!/usr/bin/env bash
# Pilot (throwaway): build SDR CFR mezzanines on a shared timeline (t=0 <=> A1 53.000 s).
set -euo pipefail
cd "/c/PROYECTOS/KORVEX DEV/KORVEXCUT/videoi"
M=.kcut/mezz; mkdir -p "$M"
TM="zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
T0=53.000; DUR=68.000; OFF=4.722
A2S=$(python -I -c "print(f'{$T0-$OFF:.3f}')")
echo "start $(date +%T)"
ffmpeg -hide_banner -loglevel error -y -ss $T0 -i "crudo 1.MOV" -t $DUR -map 0:a:0 -af "aresample=48000:resampler=soxr" -ac 1 -c:a pcm_s16le "$M/a1_voice.wav"
ffmpeg -hide_banner -loglevel error -y -ss $A2S -i "crudo 2.MOV" -t $DUR -map 0:a:0 -af "aresample=48000:resampler=soxr" -ac 1 -c:a pcm_s16le "$M/a2_check.wav"
echo "audio done $(date +%T)"
ffmpeg -hide_banner -loglevel error -y -i "video cierre.MP4" -an -vf "fps=30,format=yuv420p" -c:v libx264 -preset veryfast -crf 14 -g 15 "$M/ferrari.mp4"
ffmpeg -hide_banner -loglevel error -y -i "higgsfield.mp4" -an -vf "fps=30,format=yuv420p" -c:v libx264 -preset veryfast -crf 14 -g 15 "$M/screen.mp4"
echo "inserts done $(date +%T)"
ffmpeg -hide_banner -loglevel error -y -ss $T0 -i "crudo 1.MOV" -t $DUR -an -vf "fps=30,scale=1440:2560:flags=lanczos,$TM" -c:v libx264 -preset veryfast -crf 14 -g 15 -pix_fmt yuv420p "$M/a1.mp4"
echo "a1 done $(date +%T)"
ffmpeg -hide_banner -loglevel error -y -ss $A2S -i "crudo 2.MOV" -t $DUR -an -vf "fps=30,scale=1440:2560:flags=lanczos,$TM" -c:v libx264 -preset veryfast -crf 14 -g 15 -pix_fmt yuv420p "$M/a2.mp4"
echo "a2 done $(date +%T)"
for f in a1 a2 ferrari screen; do ffprobe -v error -select_streams v -show_entries stream=width,height,avg_frame_rate,nb_frames:format=duration -of compact=p=0 "$M/$f.mp4"; done
echo "EXIT=0"

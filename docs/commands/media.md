# Media Commands

## compress

Compress video files.

```bash
max media compress <input> [-q QUALITY] [-o OUTPUT]
```

## extract-audio

Extract audio from video.

```bash
max media extract-audio <input> [-o OUTPUT]
```

## convert

Convert video format.

```bash
max media convert <input> <output_format> [-o OUTPUT]
```

## trim

Trim video to specified duration.

```bash
max media trim <input> --start <seconds> --end <seconds> [-o OUTPUT]
```

## concat

Concatenate multiple videos.

```bash
max media concat "*.mp4" [-o OUTPUT]
```

## video-to-gif

Convert video to animated GIF.

```bash
max media video-to-gif <input> [-o OUTPUT]
```

## brightness

Adjust video brightness.

```bash
max media brightness <input> --value <0-2> [-o OUTPUT]
```

## color

Apply color preset to video.

```bash
max media color <input> --preset <preset> [-o OUTPUT]
```

**Presets:** vivid, vintage, noir, warm, cool, fade

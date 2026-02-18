# Config Commands

## show

Show current configuration.

```bash
max config show
```

## set

Set configuration value.

```bash
max config set <KEY> <VALUE>
```

## grab

Configure download preferences.

```bash
max config grab
```

Interactive wizard to set:
- Default video/audio quality
- Auto-strip playlist info
- Embed metadata
- Default type (video/audio)
- Default download folder
- Queue system enabled/disabled

## reset

Reset configuration to defaults.

```bash
max config reset [--global | --local]
```

## validate

Validate current configuration.

```bash
max config validate
```

## export

Export configuration to file.

```bash
max config export <file.json>
```

## import

Import configuration from file.

```bash
max config import <file.json>
```

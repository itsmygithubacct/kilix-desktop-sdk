# pcm-mixer snapshot provenance

This directory is the minimal source snapshot required by `kilix-cap`.
It was copied from the local `pcm-mixer` repository at commit
`9cc695cde53afba8b914e502056fee14caec442d` on 2026-07-21. The source
repository reported a clean `main` branch tracking `origin/main`.

Included files and snapshot hashes:

| File | SHA-256 |
|---|---|
| `include/pcm_mixer.h` | `d27b0353aac1b7f23a4079ac8a3c4b49e92d3892a00b0a45875126b06b9ba8de` |
| `src/pcm_mixer.c` | `c219c0cd80311aab76c8dccc869a6d9c38d7a63d719e00d4d320acfbd83688d2` |
| `src/pcm_wav.c` | `3c0ed1c7c314ac35132346b2d2b16a36d26c5abc7de53900fcaab1634634496d` |
| `LICENSE` | `ef34479183d442f9ec37c2c53154fd8f1477c575dab7aa403660f342fba74ca3` |

pcm-mixer is MIT licensed. Its full upstream notice is retained as
`LICENSE`. It requires only C11, POSIX, pthreads, and libm; audio is streamed
to an optional command-line sink and absence or failure of that sink is a
supported silent state.

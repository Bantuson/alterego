/**
 * TikTok-style captions: a few words at a time, the word currently
 * being spoken highlighted in the accent color.
 *
 * The caption data comes from a JSON file in public/ produced by the
 * Python side (whisper word timestamps -> @remotion/captions format).
 * useDelayRender() pauses rendering until that file has loaded, so
 * frames are never rendered captionless by accident.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AbsoluteFill,
  Sequence,
  staticFile,
  useCurrentFrame,
  useDelayRender,
  useVideoConfig,
} from "remotion";
import {
  createTikTokStyleCaptions,
  type Caption,
  type TikTokPage,
} from "@remotion/captions";

// How often the caption "page" changes. Lower = fewer words at once.
const SWITCH_CAPTIONS_EVERY_MS = 1200;

const Page: React.FC<{ page: TikTokPage; accent: string }> = ({
  page,
  accent,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // The Sequence resets frame to 0 at page start; add the page offset
  // back to compare against the words' absolute timestamps.
  const absoluteTimeMs = page.startMs + (frame / fps) * 1000;

  return (
    <div
      style={{
        fontSize: 58,
        fontWeight: 800,
        textAlign: "center",
        whiteSpace: "pre-wrap",
        lineHeight: 1.3,
      }}
    >
      {page.tokens.map((token) => {
        const isActive =
          token.fromMs <= absoluteTimeMs && token.toMs > absoluteTimeMs;
        return (
          <span
            key={token.fromMs}
            style={{ color: isActive ? accent : "white" }}
          >
            {token.text}
          </span>
        );
      })}
    </div>
  );
};

export const Captions: React.FC<{ file: string; accent: string }> = ({
  file,
  accent,
}) => {
  const [captions, setCaptions] = useState<Caption[] | null>(null);
  const { delayRender, continueRender, cancelRender } = useDelayRender();
  const [handle] = useState(() => delayRender());
  const { fps } = useVideoConfig();

  const fetchCaptions = useCallback(async () => {
    try {
      const res = await fetch(staticFile(file));
      setCaptions(await res.json());
      continueRender(handle);
    } catch (e) {
      cancelRender(e);
    }
  }, [file, continueRender, cancelRender, handle]);

  useEffect(() => {
    fetchCaptions();
  }, [fetchCaptions]);

  const pages = useMemo(() => {
    if (!captions) {
      return [];
    }
    return createTikTokStyleCaptions({
      captions,
      combineTokensWithinMilliseconds: SWITCH_CAPTIONS_EVERY_MS,
    }).pages;
  }, [captions]);

  return (
    <AbsoluteFill style={{ top: "62%", height: "auto", padding: "0 80px" }}>
      {pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const startFrame = (page.startMs / 1000) * fps;
        const endFrame = Math.min(
          nextPage ? (nextPage.startMs / 1000) * fps : Infinity,
          startFrame + (SWITCH_CAPTIONS_EVERY_MS / 1000) * fps,
        );
        if (endFrame - startFrame <= 0) {
          return null;
        }
        return (
          <Sequence
            key={index}
            from={startFrame}
            durationInFrames={endFrame - startFrame}
            layout="none"
          >
            <Page page={page} accent={accent} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

/**
 * The branded social clip: 9:16, dark "tech launch" look.
 *
 * Layout, top to bottom:
 *   - hook title (fades in, slides up — first thing a scroller sees)
 *   - the talking-head video in a rounded card
 *   - TikTok-style captions with the spoken word highlighted
 *   - handle + progress bar pinned to the bottom
 *
 * Everything animates via useCurrentFrame()+interpolate() — CSS
 * animations don't work in Remotion because every frame is rendered
 * as an independent screenshot.
 */
import {
  AbsoluteFill,
  Easing,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Video } from "@remotion/media";
import { Captions } from "./Captions";

export const FPS = 30;

export type ClipProps = {
  videoFile: string;
  captionsFile: string;
  title: string;
  handle: string;
  accent: string;
  durationInSeconds: number;
};

const FONT =
  "'Inter', -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

export const Clip: React.FC<ClipProps> = ({
  videoFile,
  captionsFile,
  title,
  handle,
  accent,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();

  // Title: fade + rise over the first 0.6s.
  const titleIn = interpolate(frame, [0, 0.6 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const progress = frame / durationInFrames;

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(180deg, #0b0f1d 0%, #131a2e 100%)",
        fontFamily: FONT,
        padding: 64,
        justifyContent: "flex-start",
      }}
    >
      {/* Hook title */}
      <div
        style={{
          opacity: titleIn,
          transform: `translateY(${(1 - titleIn) * 40}px)`,
          color: "white",
          fontSize: 72,
          fontWeight: 800,
          lineHeight: 1.15,
          letterSpacing: -1.5,
          marginTop: 60,
        }}
      >
        {title}
        <div
          style={{
            width: 140,
            height: 10,
            borderRadius: 5,
            background: accent,
            marginTop: 28,
          }}
        />
      </div>

      {/* The talking head, in a rounded card */}
      <div
        style={{
          marginTop: 70,
          borderRadius: 32,
          overflow: "hidden",
          boxShadow: "0 30px 80px rgba(0,0,0,0.55)",
          aspectRatio: "4 / 3",
          width: "100%",
        }}
      >
        <Video
          src={staticFile(videoFile)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      {/* Word-timed captions */}
      <Captions file={captionsFile} accent={accent} />

      {/* Handle + progress bar */}
      <div
        style={{
          position: "absolute",
          bottom: 64,
          left: 64,
          right: 64,
          color: "rgba(255,255,255,0.55)",
          fontSize: 34,
          fontWeight: 600,
          textAlign: "center",
        }}
      >
        {handle}
        <div
          style={{
            marginTop: 24,
            height: 8,
            borderRadius: 4,
            background: "rgba(255,255,255,0.12)",
          }}
        >
          <div
            style={{
              width: `${progress * 100}%`,
              height: "100%",
              borderRadius: 4,
              background: accent,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

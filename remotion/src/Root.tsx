import "./index.css";
import { Composition } from "remotion";
import { Clip, ClipProps, FPS } from "./Clip";

/**
 * One composition, "Clip", fully driven by props: the Python side
 * writes a props JSON (which video, which captions, title, handle)
 * and renders with `npx remotion render Clip --props=...`.
 *
 * 1080x1920 = 9:16 vertical, the format every short-form platform
 * wants. Duration comes from the props (Python measures the video
 * with ffmpeg) via calculateMetadata.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Clip"
      component={Clip}
      fps={FPS}
      width={1080}
      height={1920}
      durationInFrames={10 * FPS}
      defaultProps={
        {
          videoFile: "clip.mp4",
          captionsFile: "captions.json",
          title: "Building a CV pipeline on 4GB of RAM",
          handle: "@alterego",
          accent: "#39E508",
          durationInSeconds: 10,
        } satisfies ClipProps
      }
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.ceil(props.durationInSeconds * FPS),
      })}
    />
  );
};

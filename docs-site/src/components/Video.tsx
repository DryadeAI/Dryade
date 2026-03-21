import React from 'react';

interface VideoProps {
  src: string;
  title: string;
  poster?: string;
}

export default function Video({src, title, poster}: VideoProps): React.JSX.Element {
  return (
    <figure className="video-container">
      <video
        controls
        preload="metadata"
        poster={poster}
        aria-label={title}
      >
        <source src={src} />
        Your browser does not support the video element.
      </video>
      {title && <figcaption>{title}</figcaption>}
    </figure>
  );
}

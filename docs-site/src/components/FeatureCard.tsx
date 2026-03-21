import React from 'react';
import Link from '@docusaurus/Link';

interface FeatureCardProps {
  title: string;
  description: string;
  icon: string;
  link?: string;
}

export default function FeatureCard({title, description, icon, link}: FeatureCardProps): React.JSX.Element {
  const content = (
    <div className="feature-card">
      <div className="feature-card__icon">{icon}</div>
      <div className="feature-card__title">{title}</div>
      <p className="feature-card__description">{description}</p>
    </div>
  );

  if (link) {
    return <Link to={link}>{content}</Link>;
  }

  return content;
}

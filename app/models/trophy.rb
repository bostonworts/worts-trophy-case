class Trophy < ApplicationRecord
  belongs_to :user

  validates :bjcp_score, inclusion: { in: 1..50 }
  validates :competition_date, presence: true
  validates :competition_url, presence: true
  validates :place, inclusion: { allow_nil: true, in: 1..4 }
  validates :place_context, inclusion: { allow_nil: true, in: %w(best_of_show category) }
end

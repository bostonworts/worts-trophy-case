class Trophy < ApplicationRecord
  PLACE_CONTEXTS = %w(best_of_show category)

  belongs_to :competition
  belongs_to :subcategory
  belongs_to :user
  delegate :name, :url, to: :competition, prefix: true
  delegate :season, to: :competition
  delegate :bjcp_id, :name, to: :subcategory, prefix: true
  has_one_attached :photo

  validates :bjcp_score, numericality: { greater_than: 0, less_than: 51 }
  validates :competition, presence: true
  validates :place, inclusion: { allow_nil: true, in: 1..4 }
  validates :place_context, inclusion: { allow_nil: true, in: PLACE_CONTEXTS }

  validates :place, presence: true, if: -> { place_context.present? }
  validates :place_context, presence: true, if: -> { place.present? }

  scope :date_descending, -> {
    joins(:competition).merge(Competition.order(date: :desc))
  }
  scope :in_season, ->(season) {
    joins(:competition).merge(Competition.in_season(season))
  }
  scope :placed, -> { where.not(place: nil) }
  scope :placed_in, ->(context) {
    placed.where(place_context: context)
  }

  before_validation do
    # Don't allow blank string for place_context
    self.place_context = place_context.presence
  end

  def leaderboard_score
    return 0 unless competition.gives_leaderboard_points?

    if place
      bos_multiplier = placed_in_best_of_show? ? 2 : 1
      competition_bonus = competition.high_profile? ? 0.5 : 0
      base_leaderboard_score * bos_multiplier + competition_bonus
    else
      0
    end
  end

  def place_description
    if place
      "#{place.ordinalize} in #{place_context.titleize}"
    end
  end

  private

  def base_leaderboard_score
    case place
    when 1 then 3
    when 2 then 2
    when 3 then 1
    when 4 then 0.5
    else
      fail "Unexpected place #{place}"
    end
  end

  def placed_in_best_of_show?
    place_context == "best_of_show"
  end
end

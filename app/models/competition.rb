class Competition < ApplicationRecord
  has_many :trophies

  validates :name, presence: true
  validates :date, presence: true
  validates :url, presence: true
  validates :competition_type, inclusion: { in: CompetitionType::TYPES }

  scope :in_season, ->(season) {
    where(date: season.date_range)
  }
  scope :reverse_chronological, -> {
    order(date: :desc)
  }

  def self.seasons_descending
    pluck(:date).map do |date|
      Season.for_date(date)
    end.uniq.sort.reverse
  end

  def high_profile?
    CompetitionType.high_profile?(competition_type)
  end

  def medal_counts(context)
    trophies.placed_in(context).group(:place).order(:place).count.map do |place, count|
      [Medal.new(place, context), count]
    end
  end

  def description
    "#{date.year}: #{name}"
  end

  def season
    Season.for_date(date)
  end
end

class Competition < ApplicationRecord
  validates :name, presence: true
  validates :date, presence: true
  validates :url, presence: true
  validates :competition_type, inclusion: { in: CompetitionType::TYPES }

  scope :in_season, ->(season) {
    where(date: season.date_range)
  }

  def self.seasons_descending
    pluck(:date).map do |date|
      Season.for_date(date)
    end.uniq.sort.reverse
  end

  def description
    "#{date.year}: #{name}"
  end

  def season
    Season.for_date(date)
  end
end

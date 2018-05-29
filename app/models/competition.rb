class Competition < ApplicationRecord
  validates :name, presence: true
  validates :date, presence: true
  validates :url, presence: true
  validates :competition_type, inclusion: { in: CompetitionType::TYPES }

  scope :in_year, ->(year) {
    where("EXTRACT(YEAR from date) = ?", year)
  }

  def self.years_descending
    pluck(
      Arel.sql("DISTINCT extract(year from date)")
    ).map(&:to_i).sort.reverse
  end

  def description
    "#{date.year}: #{name}"
  end
end
